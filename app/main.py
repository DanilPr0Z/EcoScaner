from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.deps import DEVICE_ID_HEADER
from app.db.base import Base
from app.db.seed import seed_categories
from app.db.session import AsyncSessionLocal, engine
from app.services.recognition.registry import get_classifier


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Проверяем модель сразу: неверный CLASSIFIER должен ронять приложение на старте,
    # а не на первом сканировании.
    classifier = get_classifier()
    # Веса YOLO грузятся секунды — прогреваем заранее, иначе первый пользователь ждёт.
    warmup = getattr(classifier, "warmup", None)
    if callable(warmup):
        await asyncio.to_thread(warmup)

    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await seed_categories(session)

    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Бэкенд приложения BinGo: справочник отходов, распознавание предмета на фото "
        "и профиль пользователя. Пользователь анонимный — идентифицируется заголовком "
        f"`{DEVICE_ID_HEADER}` (UUID, который фронт генерирует один раз и хранит у себя)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Картинки справочника. Готовятся скриптом prediction/build_guide_images.py;
# если его не запускали, каталога нет — раздавать нечего, и это не ошибка.
STATIC_DIR = Path(__file__).resolve().parents[1] / "app" / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
