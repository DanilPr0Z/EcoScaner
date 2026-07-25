from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.category import CategoryBase
from app.schemas.common import CamelModel
from app.services.recognition.base import Box, TechRow


class ScanResult(CamelModel):
    """Ответ на сканирование: предсказание + весь контент категории.

    Одним запросом заполняется вся правая колонка экрана сканера.
    """

    scan_id: str
    object_name: str
    confidence: float
    is_manual: bool
    category: CategoryBase
    boxes: list[Box] = Field(default_factory=list)
    tech: list[TechRow] = Field(default_factory=list)
    points_awarded: int
    total_points: int
    created_at: datetime


class ManualScanRequest(CamelModel):
    """Пользователь выбрал категорию руками — например, после неудачного распознавания."""

    category_id: str


class CorrectionRequest(CamelModel):
    """«Модель ошиблась? Исправьте» — верная категория для уже сделанного скана."""

    category_id: str
