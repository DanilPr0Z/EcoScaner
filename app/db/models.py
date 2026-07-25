from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """SQLite отдаёт datetime без tzinfo — возвращаем его в UTC-осведомлённом виде."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Category(Base):
    """Тип отходов (бак). Контент сидируется из app/data/seed_data.py."""

    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    bin_label: Mapped[str] = mapped_column(String(128), nullable=False)
    hint: Mapped[str] = mapped_column(Text, nullable=False)
    about: Mapped[str] = mapped_column(Text, nullable=False)
    prep: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    decay: Mapped[str] = mapped_column(String(128), nullable=False)
    becomes: Mapped[str] = mapped_column(String(255), nullable=False)
    avoid: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    items: Mapped[list["CategoryItem"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
        order_by="CategoryItem.sort_order",
        lazy="selectin",
    )


class CategoryItem(Base):
    """Конкретный предмет в справочнике: принимают его в этот бак или нет."""

    __tablename__ = "category_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    category: Mapped[Category] = relationship(back_populates="items")


class Device(Base):
    """Анонимный пользователь. id — UUID, который фронт хранит у себя и шлёт в X-Device-Id."""

    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Scan(Base):
    """Одно сканирование: что распознали (или что выбрал пользователь вручную)."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"), nullable=False)
    object_name: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    points_awarded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: SHA-256 снимка. По нему находим прежние исправления того же кадра —
    #: пользователь не должен исправлять одно и то же дважды.
    image_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    #: Файл снимка относительно каталога хранилища. None — снимок не сохраняли.
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    category: Mapped[Category] = relationship(lazy="selectin")


class Correction(Base):
    """Пользователь нажал «Модель ошиблась» и указал верную категорию.

    Фото мы не храним, но сам факт ошибки копим — это метрика качества
    для будущей ML-модели.
    """

    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scan_id: Mapped[str | None] = mapped_column(
        ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    predicted_category_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corrected_category_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
