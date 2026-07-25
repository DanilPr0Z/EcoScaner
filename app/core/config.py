from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "BinGo API"
    api_prefix: str = "/api/v1"
    debug: bool = True

    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'bingo.db'}"

    #: Создавать недостающие таблицы при старте. Удобно в разработке — приложение
    #: поднимается одной командой. Если ведёте схему через Alembic, поставьте false
    #: и накатывайте `alembic upgrade head`.
    auto_create_tables: bool = True

    #: Какая реализация Classifier используется: "stub" — заглушка,
    #: "ml" — YOLOv8 (см. app/services/recognition/registry.py).
    classifier: str = "stub"

    #: Веса YOLO. Файла нет — ultralytics скачает при первом запуске (~87 МБ).
    yolo_weights: str = "yolov8l.pt"
    #: Порог уверенности детектора — ниже него объекты отбрасываются.
    yolo_confidence: float = 0.5

    #: Ограничения на загружаемое фото. Файл не сохраняется — только читается в память.
    max_upload_bytes: int = 10 * 1024 * 1024
    allowed_content_types: tuple[str, ...] = ("image/jpeg", "image/png", "image/webp")

    #: Источники, которым разрешён CORS (dev-серверы Vite / CRA).
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    #: Геймификация — те же числа, что были в дизайне (метод record()).
    points_per_scan: int = 10
    points_for_new_category: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
