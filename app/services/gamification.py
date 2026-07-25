"""Очки, серия дней и бейджи.

Логика повторяет дизайн один-в-один (методы `record()` и `renderVals()`
в BinGo.dc.html), чтобы поведение приложения после переезда на сервер
не изменилось.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.data.seed_data import MAIN_CATEGORY_IDS
from app.db.models import Category, Device, Scan, ensure_utc
from app.schemas.profile import BadgeOut, MixEntry, ProfileOut


async def award_points(session: AsyncSession, device: Device, category_id: str) -> int:
    """Начисляет очки за скан и возвращает начисленное.

    Вызывать до создания самого скана: «первая ли это категория» считается
    по уже существующей истории.
    """
    seen = await session.scalar(
        select(func.count())
        .select_from(Scan)
        .where(Scan.device_id == device.id, Scan.category_id == category_id)
    )
    awarded = settings.points_per_scan + (0 if seen else settings.points_for_new_category)
    device.points += awarded
    return awarded


def compute_streak(days: set[date], today: date | None = None) -> int:
    """Сколько дней подряд, считая от сегодня, пользователь что-то сканировал."""
    cursor = today or datetime.now(UTC).date()
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def build_badges(scan_count: int, used_category_ids: set[str], streak: int) -> list[BadgeOut]:
    main_used = used_category_ids & set(MAIN_CATEGORY_IDS)
    return [
        BadgeOut(
            id="first_scan",
            name="Первый скан",
            description="Отсканируйте любой предмет",
            achieved=scan_count >= 1,
        ),
        BadgeOut(
            id="ten_scans",
            name="Разбираюсь",
            description="10 сканирований",
            achieved=scan_count >= 10,
        ),
        BadgeOut(
            id="all_five_bins",
            name="Все пять баков",
            description="Найдите предметы всех пяти типов",
            achieved=len(main_used) >= len(MAIN_CATEGORY_IDS),
        ),
        BadgeOut(
            id="week_streak",
            name="Неделя привычки",
            description="7 дней сортировки подряд",
            achieved=streak >= 7,
        ),
        BadgeOut(
            id="hazardous",
            name="Осторожно, опасный",
            description="Распознайте особый отход",
            achieved="special" in used_category_ids,
        ),
    ]


async def build_profile(session: AsyncSession, device: Device) -> ProfileOut:
    scans = list(
        (
            await session.scalars(
                select(Scan).where(Scan.device_id == device.id).order_by(Scan.created_at.desc())
            )
        ).all()
    )
    categories = {c.id: c for c in (await session.scalars(select(Category).order_by(Category.sort_order))).all()}

    counts: dict[str, int] = {}
    days: set[date] = set()
    for scan in scans:
        counts[scan.category_id] = counts.get(scan.category_id, 0) + 1
        days.add(ensure_utc(scan.created_at).date())

    total = len(scans) or 1
    mix = [
        MixEntry(
            category_id=category_id,
            category_name=categories[category_id].name if category_id in categories else category_id,
            category_color=categories[category_id].color if category_id in categories else "#A3AB9A",
            count=count,
            share=round(count / total, 4),
        )
        for category_id, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]

    streak = compute_streak(days)
    used = set(counts)

    return ProfileOut(
        device_id=device.id,
        points=device.points,
        scan_count=len(scans),
        streak=streak,
        categories_used=len(used),
        total_categories=len(categories),
        mix=mix,
        badges=build_badges(len(scans), used, streak),
    )
