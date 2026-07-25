from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.seed_data import CATEGORIES
from app.db.models import Category, CategoryItem


async def seed_categories(session: AsyncSession) -> None:
    """Идемпотентно приводит справочник в БД к тому, что лежит в seed_data.

    Вызывается при каждом старте: правка контента в seed_data.py
    подхватывается перезапуском, дубликатов не появляется.
    """
    existing = {c.id: c for c in (await session.scalars(select(Category))).all()}

    for order, seed in enumerate(CATEGORIES):
        category = existing.get(seed["id"])
        if category is None:
            category = Category(id=seed["id"])
            session.add(category)

        category.name = seed["name"]
        category.color = seed["color"]
        category.bin_label = seed["bin_label"]
        category.hint = seed["hint"]
        category.about = seed["about"]
        category.prep = list(seed["prep"])
        category.decay = seed["decay"]
        category.becomes = seed["becomes"]
        category.avoid = seed["avoid"]
        category.sort_order = order

        # Предметы переписываем целиком — их немного, а зависимостей на них нет.
        await session.execute(delete(CategoryItem).where(CategoryItem.category_id == seed["id"]))
        for item_order, item in enumerate(seed["items"]):
            session.add(
                CategoryItem(
                    category_id=seed["id"],
                    name=item["name"],
                    is_accepted=item["ok"],
                    note=item["note"],
                    sort_order=item_order,
                )
            )

    await session.commit()
