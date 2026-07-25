from __future__ import annotations

from datetime import datetime

from app.schemas.common import CamelModel


class HistoryEntry(CamelModel):
    id: str
    category_id: str
    category_name: str
    category_color: str
    object_name: str
    confidence: float
    is_manual: bool
    created_at: datetime


class MixEntry(CamelModel):
    """Доля категории в истории — полоса распределения на экране профиля."""

    category_id: str
    category_name: str
    category_color: str
    count: int
    share: float


class BadgeOut(CamelModel):
    id: str
    name: str
    description: str
    achieved: bool


class ProfileOut(CamelModel):
    device_id: str
    points: int
    scan_count: int
    streak: int
    categories_used: int
    total_categories: int
    mix: list[MixEntry]
    badges: list[BadgeOut]


class HistoryOut(CamelModel):
    total: int
    items: list[HistoryEntry]
