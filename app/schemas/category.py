from __future__ import annotations

from app.schemas.common import CamelModel


class CategoryItemOut(CamelModel):
    name: str
    is_accepted: bool
    note: str


class CategoryBase(CamelModel):
    """Категория без списка предметов — этого хватает карточке результата сканирования."""

    id: str
    name: str
    color: str
    bin_label: str
    hint: str
    about: str
    prep: list[str]
    decay: str
    becomes: str
    avoid: str
    #: Картинка категории. None, если файла нет — интерфейс просто её не покажет.
    image_url: str | None = None


class CategoryOut(CategoryBase):
    """Полная категория со справочником предметов."""

    items: list[CategoryItemOut]


class GuideSearchItem(CamelModel):
    """Строка результата поиска по справочнику — предмет вместе со своей категорией."""

    name: str
    note: str
    is_accepted: bool
    category_id: str
    category_name: str
    category_color: str
    #: Поля, за которые строка попала в выдачу: name, note, category.
    matched_in: list[str]
    #: Вес совпадения. Выдача уже отсортирована по нему, пересчитывать не нужно.
    score: float


class GuideSearchCategory(CamelModel):
    """Категория, чей собственный текст (описание, подсказка, подготовка) отвечает запросу."""

    id: str
    name: str
    color: str
    bin_label: str
    #: Поля, где нашлось: name, bin, about, hint, avoid, prep, becomes, decay.
    matched_in: list[str]
    score: float


class GuideSearchResult(CamelModel):
    query: str
    #: Сколько предметов нашлось всего — до применения limit.
    total: int
    items: list[GuideSearchItem]
    categories: list[GuideSearchCategory]
