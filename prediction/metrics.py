"""Сводка обучения: точность и потери по эпохам.

Ultralytics пишет ход обучения в runs/<name>/results.csv. Здесь он превращается
в компактный prediction/metrics.json, который отдаёт бэкенд и показывает
интерфейс — чтобы смотреть на цифры не приходилось лезть в логи обучения.

Файл создаётся автоматически в конце обучения. Пересобрать по готовому запуску:

    python -m prediction.metrics
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "runs" / "realwaste"
DEFAULT_OUTPUT = PROJECT_ROOT / "prediction" / "metrics.json"

#: Колонки results.csv → наши имена.
_COLUMNS = {
    "train/loss": "trainLoss",
    "val/loss": "valLoss",
    "metrics/accuracy_top1": "top1",
    "metrics/accuracy_top5": "top5",
}


def _read_history(results_csv: Path) -> list[dict[str, float]]:
    history: list[dict[str, float]] = []
    with results_csv.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            point: dict[str, float] = {"epoch": int(float(row["epoch"]))}
            for column, key in _COLUMNS.items():
                raw = (row.get(column) or "").strip()
                if raw:
                    point[key] = round(float(raw), 4)
            history.append(point)
    return history


def build_metrics(
    run_dir: Path = DEFAULT_RUN_DIR,
    classes: list[str] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    results_csv = run_dir / "results.csv"
    if not results_csv.exists():
        raise FileNotFoundError(
            f"Не найден {results_csv}. Сначала обучите модель: "
            "python -m prediction.train_classifier"
        )

    history = _read_history(results_csv)
    if not history:
        raise ValueError(f"{results_csv} пуст — обучение не дало ни одной эпохи.")

    # Лучшая эпоха — по top-1, как её выбирает и сам ultralytics для best.pt.
    best = max(history, key=lambda point: point.get("top1", 0.0))

    return {
        "dataset": "RealWaste",
        "model": model or _read_model_name(run_dir),
        "trainedAt": datetime.fromtimestamp(results_csv.stat().st_mtime, UTC).isoformat(),
        "epochs": len(history),
        "classes": classes or [],
        "best": best,
        "history": history,
    }


def _read_model_name(run_dir: Path) -> str:
    args = run_dir / "args.yaml"
    if not args.exists():
        return "yolov8-cls"
    for line in args.read_text(encoding="utf-8").splitlines():
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return "yolov8-cls"


def save_metrics(
    run_dir: Path = DEFAULT_RUN_DIR,
    output: Path = DEFAULT_OUTPUT,
    classes: list[str] | None = None,
) -> dict[str, Any]:
    metrics = build_metrics(run_dir, classes=classes)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metrics


def format_table(metrics: dict[str, Any]) -> str:
    """Таблица для вывода в консоль после обучения."""
    lines = [
        f"{'эпоха':>6} {'train loss':>11} {'val loss':>9} {'top-1':>7} {'top-5':>7}",
        "-" * 44,
    ]
    for point in metrics["history"]:
        lines.append(
            f"{point['epoch']:>6} {point.get('trainLoss', 0):>11.4f} "
            f"{point.get('valLoss', 0):>9.4f} {point.get('top1', 0):>7.3f} "
            f"{point.get('top5', 0):>7.3f}"
        )
    best = metrics["best"]
    lines.append("-" * 44)
    lines.append(
        f"лучшая эпоха {best['epoch']}: top-1 {best.get('top1', 0):.3f}, "
        f"top-5 {best.get('top5', 0):.3f}, val loss {best.get('valLoss', 0):.4f}"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    saved = save_metrics()
    print(format_table(saved))
    print(f"\nСводка сохранена: {DEFAULT_OUTPUT.relative_to(PROJECT_ROOT)}")
