"""Граница между приложением и ML.

Здесь описан единственный контракт, который должна выполнить модель
распознавания. Сейчас за ним стоит заглушка (`stub.StubClassifier`),
позже появится реальная реализация — роутеры, схемы и фронт при этом
не меняются.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field

from app.schemas.common import CamelModel


class Box(CamelModel):
    """Рамка вокруг найденного объекта.

    Координаты — в процентах от размеров изображения, потому что сам файл
    мы не храним: фронт рисует рамку поверх своего локального превью.
    """

    left: float = Field(ge=0, le=100)
    top: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    label: str


class TechRow(CamelModel):
    """Строка блока «Что увидела нейросеть»."""

    label: str
    score: str


class Prediction(CamelModel):
    """Сырой результат модели, ещё без контента справочника."""

    category_id: str
    object_name: str
    confidence: float = Field(ge=0, le=1)
    boxes: list[Box] = Field(default_factory=list)
    tech: list[TechRow] = Field(default_factory=list)


@runtime_checkable
class Classifier(Protocol):
    """Контракт модели распознавания.

    `predict` возвращает None, если на фото не найдено ничего похожего на
    известный тип отхода — роутер превратит это в 422 с текстом для
    экрана ошибки, где пользователь выбирает категорию вручную.
    """

    name: str

    async def predict(self, image: bytes, content_type: str) -> Prediction | None: ...
