from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Category, CategoryItem
from app.schemas.category import GuideSearchCategory, GuideSearchItem

#: Где лежат картинки справочника. Готовятся prediction/build_guide_images.py.
GUIDE_IMAGES = Path(__file__).resolve().parents[2] / "app" / "static" / "guide"


def image_url(category_id: str) -> str | None:
    """Ссылка на картинку категории — или None, если файла нет.

    Проверяем наличие файла, а не подставляем путь вслепую: иначе интерфейс
    будет показывать битые картинки на машине, где скрипт не запускали.
    """
    return f"/static/guide/{category_id}.jpg" if (GUIDE_IMAGES / f"{category_id}.jpg").exists() else None


def item_image_url(category_id: str, index: int) -> str | None:
    """Ссылка на картинку конкретного предмета. Имя файла — категория и номер.

    Номер берётся из порядка предметов в справочнике: он задан в seed_data
    и не меняется, поэтому картинки не перепутаются местами.
    """
    name = f"{category_id}-{index}.jpg"
    return f"/static/guide/items/{name}" if (GUIDE_IMAGES / "items" / name).exists() else None
from app.services.text_search import score_text, tokenize

#: Поля предмета и их вес. Совпадение в названии важнее, чем в примечании,
#: а название категории — самый слабый повод показать предмет.
_ITEM_WEIGHTS = {"name": 10.0, "note": 5.0, "category": 4.0}

#: Поля категории. Ищем и по описанию, подсказке и шагам подготовки —
#: так «метан» приводит к органике, а «маркировка 1» к пластику.
_CATEGORY_WEIGHTS = {
    "name": 10.0,
    "bin": 5.0,
    "about": 3.0,
    "hint": 3.0,
    "avoid": 3.0,
    "prep": 2.0,
    "becomes": 2.0,
    "decay": 2.0,
}

_Field = tuple[str, float, tuple[str, ...]]


async def list_categories(session: AsyncSession) -> list[Category]:
    stmt = select(Category).order_by(Category.sort_order)
    return list((await session.scalars(stmt)).all())


async def get_category(session: AsyncSession, category_id: str) -> Category | None:
    return await session.get(Category, category_id)


def _score(tokens: tuple[str, ...], fields: list[_Field]) -> tuple[float, list[str]]:
    """Оценивает набор полей против запроса.

    Каждое слово запроса должно найтись хотя бы в одном поле (AND), иначе
    результат отбрасывается. Возвращает суммарный вес и поля, которые дали
    совпадение, — фронт показывает, за что строка попала в выдачу.
    """
    total = 0.0
    matched: list[str] = []

    for token in tokens:
        best = 0.0
        best_field: str | None = None
        for key, weight, words in fields:
            value = score_text(token, words) * weight
            if value > best:
                best, best_field = value, key

        if not best:
            return 0.0, []

        total += best
        if best_field and best_field not in matched:
            matched.append(best_field)

    return total, matched


def _item_fields(item: CategoryItem, category: Category) -> list[_Field]:
    return [
        ("name", _ITEM_WEIGHTS["name"], tokenize(item.name)),
        ("note", _ITEM_WEIGHTS["note"], tokenize(item.note)),
        ("category", _ITEM_WEIGHTS["category"], tokenize(category.name)),
    ]


def _category_fields(category: Category) -> list[_Field]:
    return [
        ("name", _CATEGORY_WEIGHTS["name"], tokenize(category.name)),
        ("bin", _CATEGORY_WEIGHTS["bin"], tokenize(category.bin_label)),
        ("about", _CATEGORY_WEIGHTS["about"], tokenize(category.about)),
        ("hint", _CATEGORY_WEIGHTS["hint"], tokenize(category.hint)),
        ("avoid", _CATEGORY_WEIGHTS["avoid"], tokenize(category.avoid)),
        ("prep", _CATEGORY_WEIGHTS["prep"], tokenize(" ".join(category.prep))),
        ("becomes", _CATEGORY_WEIGHTS["becomes"], tokenize(category.becomes)),
        ("decay", _CATEGORY_WEIGHTS["decay"], tokenize(category.decay)),
    ]


async def search(
    session: AsyncSession, query: str, limit: int = 50
) -> tuple[list[GuideSearchItem], int, list[GuideSearchCategory]]:
    """Поиск по справочнику: предметы и категории, отсортированные по релевантности.

    Возвращает (предметы с учётом limit, всего найдено предметов, категории).
    """
    tokens = tokenize(query)
    if not tokens:
        return [], 0, []

    categories = await list_categories(session)
    by_id = {category.id: category for category in categories}

    rows = (
        await session.execute(
            select(CategoryItem).order_by(CategoryItem.category_id, CategoryItem.sort_order)
        )
    ).scalars()

    scored_items: list[tuple[float, int, int, GuideSearchItem]] = []
    for item in rows:
        category = by_id[item.category_id]
        score, matched_in = _score(tokens, _item_fields(item, category))
        if not score:
            continue
        scored_items.append(
            (
                score,
                category.sort_order,
                item.sort_order,
                GuideSearchItem(
                    name=item.name,
                    note=item.note,
                    is_accepted=item.is_accepted,
                    category_id=category.id,
                    category_name=category.name,
                    category_color=category.color,
                    matched_in=matched_in,
                    score=round(score, 2),
                ),
            )
        )

    # По убыванию релевантности; при равном весе — порядок справочника.
    scored_items.sort(key=lambda row: (-row[0], row[1], row[2]))

    scored_categories: list[tuple[float, int, GuideSearchCategory]] = []
    for category in categories:
        score, matched_in = _score(tokens, _category_fields(category))
        if not score:
            continue
        scored_categories.append(
            (
                score,
                category.sort_order,
                GuideSearchCategory(
                    id=category.id,
                    name=category.name,
                    color=category.color,
                    bin_label=category.bin_label,
                    matched_in=matched_in,
                    score=round(score, 2),
                ),
            )
        )
    scored_categories.sort(key=lambda row: (-row[0], row[1]))

    return (
        [item for *_, item in scored_items[:limit]],
        len(scored_items),
        [category for *_, category in scored_categories],
    )
