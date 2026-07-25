from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import CamelModel
from app.services.recognition.registry import get_classifier

router = APIRouter(tags=["service"])


class HealthOut(CamelModel):
    status: str
    app_name: str
    classifier: str


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Статус сервиса и активная модель — фронт показывает индикатор в шапке сканера."""
    return HealthOut(status="ok", app_name=settings.app_name, classifier=get_classifier().name)
