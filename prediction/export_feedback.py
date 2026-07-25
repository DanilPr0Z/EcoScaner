"""Готовит из исправлений пользователей обучающую выборку.

Каждое исправление — это размеченный человеком пример: снимок и категория,
которую человек посчитал верной. Причём это ровно те кадры, на которых модель
ошиблась, и сняты они в тех условиях, в которых приложением реально пользуются.
Ценность таких примеров выше, чем у случайных снимков из открытых датасетов.

Скрипт раскладывает их по папкам классов рядом с остальными источниками —
дальше обучение подхватит их само.

    python -m prediction.export_feedback
    python -m prediction.export_feedback --min-per-class 5

Осторожно с малым числом примеров: десяток снимков одного предмета не научит
модель, зато может сместить её в сторону этого предмета. Порог --min-per-class
не даёт выгрузить класс, примеров в котором заведомо мало.
"""

from __future__ import annotations

import argparse
import asyncio
import collections
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes"

#: Категория справочника → класс обучающей выборки. Обратное соответствие
#: к WASTE_CLASSES_RU: у категории несколько классов, для выгрузки берём
#: самый общий из них.
CATEGORY_TO_CLASS: dict[str, str] = {
    "plastic": "Plastic",
    "glass": "Glass",
    "paper": "Paper",
    "metal": "Metal",
    "organic": "Food Organics",
    "special": "Battery",
    "other": "Miscellaneous Trash",
}


async def collect() -> list[tuple[str, Path]]:
    """Возвращает пары (категория, файл) по всем исправлённым сканам."""
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from sqlalchemy import select

    from app.db.models import Correction, Scan
    from app.db.session import AsyncSessionLocal
    from app.services.uploads import uploads_dir

    async with AsyncSessionLocal() as session:
        statement = (
            select(Scan)
            .join(Correction, Correction.scan_id == Scan.id)
            .where(Scan.image_path.is_not(None))
        )
        scans = (await session.scalars(statement)).unique().all()

    root = uploads_dir()
    pairs: list[tuple[str, Path]] = []
    for scan in scans:
        path = root / scan.image_path
        if path.exists():
            pairs.append((scan.category_id, path))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Выгрузка исправлений в обучающую выборку")
    parser.add_argument(
        "--min-per-class",
        type=int,
        default=5,
        help="не выгружать класс, если примеров меньше этого числа",
    )
    parser.add_argument("--dry-run", action="store_true", help="только показать, что будет")
    args = parser.parse_args()

    pairs = asyncio.run(collect())
    if not pairs:
        print("Исправлений со снимками пока нет — выгружать нечего.")
        return

    by_category: dict[str, list[Path]] = collections.defaultdict(list)
    for category, path in pairs:
        by_category[category].append(path)

    exported = 0
    for category, paths in sorted(by_category.items()):
        class_name = CATEGORY_TO_CLASS.get(category)
        if class_name is None:
            print(f"  × {category}: нет соответствующего класса")
            continue
        if len(paths) < args.min_per_class:
            print(f"  · {category:10} {len(paths):3} — мало, пропускаем (порог {args.min_per_class})")
            continue

        destination = TARGET / class_name
        if not args.dry_run:
            destination.mkdir(parents=True, exist_ok=True)
            for path in paths:
                shutil.copy2(path, destination / f"feedback_{path.name}")
        exported += len(paths)
        print(f"  ✓ {category:10} {len(paths):3} → {class_name}")

    print(f"\nВыгружено: {exported}")
    if exported and not args.dry_run:
        print("Дальше: python -m prediction.train_classifier")


if __name__ == "__main__":
    main()
