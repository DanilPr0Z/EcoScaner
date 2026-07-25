from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.common import CamelModel
from app.services.recognition.registry import get_classifier

router = APIRouter(prefix="/model", tags=["model"])

METRICS_PATH = Path(__file__).resolve().parents[3] / "prediction" / "metrics.json"


class EpochPoint(CamelModel):
    epoch: int
    train_loss: float | None = None
    val_loss: float | None = None
    top1: float | None = None
    top5: float | None = None


class ModelInfo(CamelModel):
    """Что за модель сейчас распознаёт и как она обучалась."""

    classifier: str
    trained: bool
    dataset: str | None = None
    model: str | None = None
    trained_at: str | None = None
    epochs: int | None = None
    classes: list[str] = []
    best: EpochPoint | None = None
    history: list[EpochPoint] = []


@router.get("", response_model=ModelInfo)
async def model_info() -> ModelInfo:
    """Точность и потери по эпохам — то же, что пишет обучение в results.csv.

    Если модель ещё не обучалась, отдаёт только текущий режим распознавания:
    отсутствие сводки — не ошибка, на заглушке её и не должно быть.
    """
    classifier = get_classifier().name

    if not METRICS_PATH.exists():
        return ModelInfo(classifier=classifier, trained=False)

    try:
        raw = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as cause:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Сводка обучения повреждена: {cause}",
        ) from cause

    return ModelInfo(
        classifier=classifier,
        trained=classifier != "stub",
        dataset=raw.get("dataset"),
        model=raw.get("model"),
        trained_at=raw.get("trainedAt"),
        epochs=raw.get("epochs"),
        classes=raw.get("classes", []),
        best=EpochPoint(**raw["best"]) if raw.get("best") else None,
        history=[EpochPoint(**point) for point in raw.get("history", [])],
    )


@router.get("/settings", response_model=dict)
async def model_settings() -> dict:
    """Параметры распознавания — удобно проверить, что подхватился нужный .env."""
    return {
        "classifier": settings.classifier,
        "weights": settings.waste_classifier_weights,
        "detector": settings.detector_weights or None,
        "detectorConfidence": settings.detector_confidence,
    }
