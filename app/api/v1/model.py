from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.common import CamelModel
from app.services.recognition.registry import get_classifier

router = APIRouter(prefix="/model", tags=["model"])

METRICS_PATH = Path(__file__).resolve().parents[3] / "prediction" / "metrics.json"


def _training_classes() -> set[str]:
    from prediction.train_classifier import WASTE_CLASSES_RU

    return set(WASTE_CLASSES_RU)


class EpochPoint(CamelModel):
    epoch: int
    train_loss: float | None = None
    val_loss: float | None = None
    top1: float | None = None
    top5: float | None = None


class TrainingProgress(CamelModel):
    """Ход текущей эпохи. Обновляется каждые несколько батчей."""

    epoch: int
    epochs: int
    batch: int
    batches: int
    #: Среднее значение потерь по батчам текущей эпохи. Падает — идём верно.
    mean_loss: float


class ModelInfo(CamelModel):
    """Что за модель сейчас распознаёт и как она обучалась."""

    classifier: str
    trained: bool
    #: Обучение прямо сейчас идёт — цифры будут меняться с каждой эпохой.
    in_progress: bool = False
    dataset: str | None = None
    model: str | None = None
    trained_at: str | None = None
    epochs: int | None = None
    classes: list[str] = []
    best: EpochPoint | None = None
    history: list[EpochPoint] = []
    progress: TrainingProgress | None = None


def _progress() -> TrainingProgress | None:
    """Ход текущей эпохи — его пишет обучение после каждых нескольких батчей.

    Эпоха идёт минуты, и по одним лишь итогам эпох не понять, туда ли всё
    движется. Среднее по батчам показывает направление, не дожидаясь конца.
    """
    from prediction.metrics import DEFAULT_RUN_DIR

    path = DEFAULT_RUN_DIR / "progress.json"
    if not path.exists():
        return None
    try:
        return TrainingProgress(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None  # файл могли переписать в момент чтения — не беда, придёт следующий


def _run_state() -> tuple[dict | None, bool]:
    """Сводка обучения и признак того, что оно идёт прямо сейчас.

    results.csv обучение дописывает после каждой эпохи — благодаря этому за
    прогрессом видно по ходу дела, а не только в конце. Пока считается первая
    эпоха, файла ещё нет, но запуск уже начался: об этом говорит args.yaml,
    который ultralytics пишет сразу. Такое состояние — «идёт, данных пока нет»,
    а не «модель не обучалась».
    """
    from prediction.metrics import DEFAULT_RUN_DIR, build_metrics

    started_marker = DEFAULT_RUN_DIR / "args.yaml"
    results = DEFAULT_RUN_DIR / "results.csv"
    if not started_marker.exists():
        return None, False

    # Готовая сводка появляется в самом конце. Если её нет или она старше
    # текущего запуска — обучение ещё не закончилось.
    finished = (
        METRICS_PATH.exists()
        and METRICS_PATH.stat().st_mtime >= started_marker.stat().st_mtime
    )

    if not results.exists():
        return None, not finished

    try:
        return build_metrics(DEFAULT_RUN_DIR), not finished
    except (FileNotFoundError, ValueError, OSError):
        return None, not finished


@router.get("", response_model=ModelInfo)
async def model_info() -> ModelInfo:
    """Точность и потери по эпохам — то же, что пишет обучение в results.csv.

    Пока обучение идёт, цифры отдаются по ходу дела: страница показывает
    прогресс, а не ждёт конца. Если модель ещё не обучалась, отдаётся только
    текущий режим распознавания — отсутствие сводки не ошибка.
    """
    classifier = get_classifier().name

    live, in_progress = _run_state()
    saved: dict = {}
    if METRICS_PATH.exists():
        try:
            saved = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as cause:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Сводка обучения повреждена: {cause}",
            ) from cause

    if live is None and not saved:
        return ModelInfo(
            classifier=classifier,
            trained=False,
            in_progress=in_progress,
            progress=_progress(),
        )

    if live is not None:
        raw = live
        # Список классов ведёт обучение, в results.csv его нет.
        raw["classes"] = saved.get("classes") or sorted(_training_classes())
    else:
        raw = saved

    return ModelInfo(
        in_progress=in_progress,
        progress=_progress(),
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
