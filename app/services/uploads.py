"""Хранение пользовательских снимков и память об исправлениях.

Зачем хранить. Пока снимки не сохранялись, исправление категории оставалось
пометкой в базе: пользователь поправил ответ, но учиться на этом было не на чем,
и та же фотография снова распознавалась неверно. Теперь снимок ложится на диск
и вместе с исправленной категорией становится размеченным примером.

Что это даёт сразу, не дожидаясь дообучения: у каждого снимка считается SHA-256,
и если такой кадр уже исправляли, ответ берётся из исправления. Один и тот же
файл больше не придётся поправлять дважды.

Оговорка про приватность: снимки пользователей — персональные данные. Хранение
включается настройкой STORE_UPLOADS, срок жизни неисправленных задаётся
UPLOADS_KEEP_DAYS, исправленные остаются как обучающая выборка.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Correction, Scan

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Расширение по типу содержимого. Храним как пришло, без перекодирования:
#: для дообучения важен исходный кадр, а не наша интерпретация.
_SUFFIXES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def uploads_dir() -> Path:
    path = Path(settings.uploads_dir)
    return path if path.is_absolute() else PROJECT_ROOT / path


def image_hash(image: bytes) -> str:
    return hashlib.sha256(image).hexdigest()


def save(image: bytes, digest: str, content_type: str) -> str | None:
    """Кладёт снимок на диск и возвращает путь относительно хранилища.

    Имя файла — хэш содержимого: одинаковые кадры не плодят копии, а поиск
    прежнего исправления сводится к сравнению имён.
    """
    if not settings.store_uploads:
        return None

    suffix = _SUFFIXES.get(content_type.split(";")[0].strip().lower(), ".jpg")
    # Раскладываем по первым двум символам хэша: в одном каталоге не окажется
    # десятков тысяч файлов, с которыми плохо работает и файловая система, и глаз.
    relative = f"{digest[:2]}/{digest}{suffix}"
    destination = uploads_dir() / relative
    if destination.exists():
        return relative

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image)
    return relative


async def previous_correction(session: AsyncSession, digest: str) -> str | None:
    """Категория, на которую этот же кадр уже исправляли.

    Берём самое свежее исправление: если человек передумал, верным считается
    последнее его решение.
    """
    statement = (
        select(Correction.corrected_category_id)
        .join(Scan, Scan.id == Correction.scan_id)
        .where(Scan.image_hash == digest)
        .order_by(Correction.created_at.desc())
        .limit(1)
    )
    return await session.scalar(statement)


async def cleanup(session: AsyncSession) -> int:
    """Удаляет старые снимки, которые никто не исправлял.

    Исправленные не трогаем: они и есть та самая размеченная выборка.
    """
    if not settings.store_uploads or settings.uploads_keep_days <= 0:
        return 0

    threshold = datetime.now(UTC) - timedelta(days=settings.uploads_keep_days)
    corrected = select(Correction.scan_id).where(Correction.scan_id.is_not(None))
    statement = select(Scan).where(
        Scan.image_path.is_not(None),
        Scan.created_at < threshold,
        Scan.id.not_in(corrected),
    )

    removed = 0
    for scan in (await session.scalars(statement)).all():
        path = uploads_dir() / scan.image_path
        path.unlink(missing_ok=True)
        scan.image_path = None
        removed += 1

    if removed:
        await session.commit()
    return removed
