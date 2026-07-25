"""Обучение классификатора отходов на датасете RealWaste.

Почему классификация, а не детекция. RealWaste — набор снимков по папкам-классам,
рамок в нём нет, поэтому обучить на нём детектор нельзя. Приложению детекция и не
нужна: пользователь снимает один предмет крупно, вопрос стоит «из чего это»,
а не «где это на кадре».

Запуск:

    python -m prediction.train_classifier                 # обучение с настройками по умолчанию
    python -m prediction.train_classifier --epochs 40     # дольше и точнее
    python -m prediction.train_classifier --model yolov8m-cls.pt

Датасет ожидается в realwaste-main/RealWaste (папка на класс). Скрипт сам делит
его на train/val симлинками — 666 МБ снимков не копируются.

Результат кладётся в prediction/waste_classifier.pt — этот файл подхватывает
бэкенд при CLASSIFIER=ml.
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Датасет с исходными снимками: папка на класс.
DEFAULT_SOURCE = PROJECT_ROOT / "realwaste-main" / "RealWaste"
#: Куда раскладывается train/val для ultralytics.
DEFAULT_SPLIT_DIR = PROJECT_ROOT / "datasets" / "realwaste"
#: Куда кладутся веса обученной модели.
DEFAULT_WEIGHTS = PROJECT_ROOT / "prediction" / "waste_classifier.pt"

#: Класс RealWaste → (категория справочника по-русски, название предмета).
#: Русские названия переводятся в id справочника в app/services/recognition/ml.py.
REALWASTE_CLASSES_RU: dict[str, tuple[str, str]] = {
    "Cardboard": ("бумага", "картон"),
    "Paper": ("бумага", "бумага"),
    "Glass": ("стекло", "стекло"),
    "Metal": ("металл", "металл"),
    "Plastic": ("пластик", "пластик"),
    "Food Organics": ("органика", "пищевые отходы"),
    "Vegetation": ("органика", "растительные остатки"),
    "Textile Trash": ("прочее", "текстиль"),
    "Miscellaneous Trash": ("прочее", "смешанные отходы"),
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def build_split(source: Path, target: Path, val_share: float, seed: int) -> dict[str, int]:
    """Раскладывает снимки на train/val симлинками.

    Симлинки, а не копии: датасет весит 666 МБ, дублировать его незачем.
    Разбиение детерминировано seed — повторный запуск даёт тот же split,
    иначе метрики между запусками несравнимы.
    """
    if not source.is_dir():
        raise SystemExit(
            f"Не найден датасет: {source}\n"
            "Скачайте RealWaste и положите в realwaste-main/RealWaste."
        )

    if target.exists():
        shutil.rmtree(target)

    counts: dict[str, int] = {}
    rng = random.Random(seed)

    for class_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        images = sorted(
            p for p in class_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
        )
        if not images:
            continue

        rng.shuffle(images)
        cut = max(1, round(len(images) * val_share))
        parts = {"val": images[:cut], "train": images[cut:]}

        for split, files in parts.items():
            split_dir = target / split / class_dir.name
            split_dir.mkdir(parents=True, exist_ok=True)
            for image in files:
                (split_dir / image.name).symlink_to(image.resolve())

        counts[class_dir.name] = len(images)

    if not counts:
        raise SystemExit(f"В {source} не нашлось изображений.")
    return counts


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение классификатора отходов на RealWaste")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="папка с классами")
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS, help="куда сохранить модель")
    parser.add_argument("--model", default="yolov8s-cls.pt", help="базовая модель")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--val-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default=None, help="cpu, mps или номер GPU")
    args = parser.parse_args()

    print("Готовим разбиение…")
    counts = build_split(args.source, args.split_dir, args.val_share, args.seed)
    total = sum(counts.values())
    print(f"Классов: {len(counts)}, снимков: {total}")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        category, obj = REALWASTE_CLASSES_RU.get(name, ("?", "?"))
        print(f"  {name:22} {count:5}  → {category} / {obj}")

    unmapped = set(counts) - set(REALWASTE_CLASSES_RU)
    if unmapped:
        raise SystemExit(
            f"В датасете есть классы без соответствия категории: {sorted(unmapped)}. "
            "Добавьте их в REALWASTE_CLASSES_RU."
        )

    device = args.device or pick_device()
    print(f"\nОбучаем {args.model} на {device}, {args.epochs} эпох, {args.imgsz}px…\n")

    from ultralytics import YOLO

    model = YOLO(args.model)
    model.train(
        data=str(args.split_dir),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        seed=args.seed,
        project=str(PROJECT_ROOT / "runs"),
        name="realwaste",
        exist_ok=True,
        verbose=True,
        plots=False,
    )

    best = PROJECT_ROOT / "runs" / "realwaste" / "weights" / "best.pt"
    if not best.exists():
        raise SystemExit(f"Обучение прошло, но веса не найдены: {best}")

    args.weights.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, args.weights)
    print(f"\nМодель сохранена: {args.weights.relative_to(PROJECT_ROOT)}")

    # Сводка по эпохам — её отдаёт бэкенд и показывает интерфейс,
    # чтобы за точностью и потерями не нужно было лезть в логи обучения.
    from prediction.metrics import format_table, save_metrics

    summary = save_metrics(
        run_dir=PROJECT_ROOT / "runs" / "realwaste", classes=sorted(counts)
    )
    print()
    print(format_table(summary))

    validation = YOLO(args.weights).val(data=str(args.split_dir), device=device, verbose=False)
    print(f"\nТочность top-1: {validation.top1:.3f}   top-5: {validation.top5:.3f}")


if __name__ == "__main__":
    main()
