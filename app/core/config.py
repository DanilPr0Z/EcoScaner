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

    #: Классификатор материала, обученный на RealWaste.
    #: Обучить: python -m prediction.train_classifier
    waste_classifier_weights: str = "prediction/waste_classifier.pt"

    #: Детектор COCO — нужен только для рамки вокруг предмета и уточнения
    #: названия. На выбор категории не влияет; пустая строка отключает его.
    detector_weights: str = "yolov8n.pt"
    #: Порог уверенности детектора — ниже него рамка не рисуется.
    detector_confidence: float = 0.5

    #: Сохранять снимки пользователей. Нужно для дообучения: без них исправления
    #: категорий остаются просто пометками в базе, учиться не на чем.
    store_uploads: bool = True
    #: Куда складывать снимки.
    uploads_dir: str = "storage/uploads"
    #: Сколько дней хранить снимки без исправления. Исправленные не удаляются:
    #: это размеченные человеком примеры, ради которых всё и затевалось.
    uploads_keep_days: int = 30

    #: Ограничения на загружаемое фото.
    max_upload_bytes: int = 10 * 1024 * 1024
    #: HEIC здесь не для полноты списка: это формат снимков айфона
    #: по умолчанию. С камеры в приложении кадр уходит уже как JPEG — его
    #: рисует холст, — а вот готовое фото из галереи может приехать как есть.
    #: Обычно Safari пережимает его сам, но не всегда: через «Файлы»
    #: или «Поделиться» оно уходит нетронутым и получало отказ 415.
    allowed_content_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    )

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
