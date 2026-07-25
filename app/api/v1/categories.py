from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import SessionDep
from app.schemas.category import CategoryOut, GuideSearchResult
from app.services import guide

router = APIRouter(tags=["guide"])


def _with_image(category) -> CategoryOut:  # noqa: ANN001
    """Категория и её предметы вместе со ссылками на картинки."""
    out = CategoryOut.model_validate(category)
    out.image_url = guide.image_url(category.id)
    for index, item in enumerate(out.items):
        item.image_url = guide.item_image_url(category.id, index)
    return out


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(session: SessionDep) -> list[CategoryOut]:
    """Весь справочник: 7 категорий с предметами. Используется главной, справочником и модалкой."""
    categories = await guide.list_categories(session)
    return [_with_image(c) for c in categories]


@router.get("/categories/{category_id}", response_model=CategoryOut)
async def get_category(category_id: str, session: SessionDep) -> CategoryOut:
    category = await guide.get_category(session, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Категория {category_id!r} не найдена.",
        )
    return _with_image(category)


@router.get("/guide/search", response_model=GuideSearchResult)
async def search_guide(
    session: SessionDep,
    q: str = Query(
        min_length=1,
        max_length=64,
        description="Запрос: название предмета, материал или слово из описания категории",
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Сколько предметов вернуть"),
) -> GuideSearchResult:
    """Поиск по всему тексту справочника.

    Ищет не только по названиям предметов, но и по примечаниям, описаниям
    категорий, подсказкам и шагам подготовки. Учитывает словоформы
    («бутылки» → «бутылка») и опечатку в один символ. Выдача отсортирована
    по релевантности; поле `matchedIn` говорит, где именно нашлось.
    """
    items, total, categories = await guide.search(session, q, limit=limit)
    return GuideSearchResult(query=q.strip(), total=total, items=items, categories=categories)
