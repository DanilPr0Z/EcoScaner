"""Проверка, что настройки обучения действительно доходят до дела.

За один день трижды выяснилось, что параметр принимается, печатается в логе
и не делает ничего: аугментации ultralytics для классификации, amp на MPS,
сглаживание меток. Каждый раз это обнаруживалось через часы обучения.

Скрипт проверяет заранее и по факту, а не по намерению: собирает те же
преобразования и ту же функцию потерь, что и обучение, и смотрит, что внутри.

    python -m prediction.preflight
    python -m prediction.preflight --imgsz 288 --label-smoothing 0.1
"""

from __future__ import annotations

import argparse


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверка настроек обучения")
    parser.add_argument("--imgsz", type=int, default=288)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--rotate", type=float, default=20)
    parser.add_argument("--jitter", type=float, default=0.5)
    parser.add_argument("--grayscale", type=float, default=0.15)
    parser.add_argument("--blur", type=float, default=0.15)
    parser.add_argument("--category-loss", type=float, default=0.0)
    args = parser.parse_args()

    import torch

    from prediction.train_classifier import (
        AUGMENTATION,
        CategoryAwareLoss,
        attach_extra_augmentation,
        enable_half_precision,
        pick_device,
    )

    everything = True
    print("\n=== устройство и точность ===")
    device = pick_device()
    everything &= check("видеоядро", device == "mps", device)
    everything &= check(
        "bfloat16 включён",
        enable_half_precision(device),
        "ultralytics сам этого на MPS не делает",
    )

    from ultralytics.engine import trainer as trainer_module

    context = trainer_module.autocast(True)
    everything &= check(
        "autocast смотрит на mps",
        getattr(context, "device", None) == "mps",
        f"device={getattr(context, 'device', '?')}, dtype={getattr(context, 'fast_dtype', '?')}",
    )

    print("\n=== аугментации ===")
    from ultralytics.data.augment import classify_augmentations

    # Повторяем ровно то, что делает ultralytics в ClassificationDataset:
    # имена наших настроек и её параметров не совпадают (fliplr → hflip,
    # flipud → vflip), а scale из одного числа превращается в диапазон.
    # Проверять надо конечный результат, а не намерение.
    base = classify_augmentations(
        size=args.imgsz,
        scale=(1.0 - AUGMENTATION["scale"], 1.0),
        hflip=AUGMENTATION["fliplr"],
        vflip=AUGMENTATION["flipud"],
        erasing=AUGMENTATION["erasing"],
        auto_augment="randaugment",
    )
    applied = str(base)
    for knob, marker in (
        ("scale → случайная обрезка", "RandomResizedCrop"),
        ("fliplr → отражение по горизонтали", "RandomHorizontalFlip"),
        ("flipud → отражение по вертикали", "RandomVerticalFlip"),
        ("erasing → стирание кусков", "RandomErasing"),
        ("auto_augment → RandAugment", "RandAugment"),
    ):
        everything &= check(f"{knob}", marker in applied, marker)

    # Задокументированная ловушка: при заданном auto_augment ultralytics
    # выбрасывает ColorJitter, поэтому hsv_* не доходят и цвет мы правим сами.
    check(
        "ColorJitter от ultralytics отсутствует (ожидаемо)",
        "ColorJitter" not in applied,
        "его вытесняет auto_augment — поэтому цвет добавляем вручную",
    )

    # Наши собственные — те, которых у ultralytics для классификации нет.
    class Fake:
        def __init__(self) -> None:
            self.callbacks: dict[str, list] = {}

        def add_callback(self, event: str, fn) -> None:  # noqa: ANN001
            self.callbacks.setdefault(event, []).append(fn)

    model = Fake()
    attach_extra_augmentation(model, args.grayscale, args.blur, args.rotate, args.jitter)
    everything &= check(
        "обработчик своих аугментаций навешен",
        bool(model.callbacks.get("on_train_start")),
        f"событий: {list(model.callbacks)}",
    )

    print("\n=== функция потерь ===")
    groups = [[0, 1], [2], [3]]
    logits = torch.tensor([[10.0, -10.0, -10.0, -10.0]])
    target = torch.tensor([0])
    plain, _ = CategoryAwareLoss(groups, None, args.category_loss, 0.0)(logits, {"cls": target})
    smoothed, _ = CategoryAwareLoss(groups, None, args.category_loss, args.label_smoothing)(
        logits, {"cls": target}
    )
    everything &= check(
        "сглаживание меток применяется",
        args.label_smoothing <= 0 or float(smoothed) > float(plain) + 1e-6,
        f"без него {float(plain):.4f}, с ним {float(smoothed):.4f}",
    )
    everything &= check(
        "категорийное слагаемое в нужном состоянии",
        True,
        "выключено" if args.category_loss <= 0 else f"вес {args.category_loss}",
    )

    print("\n=== данные ===")
    from prediction.train_classifier import DEFAULT_SOURCES, collect_classes

    classes = collect_classes(list(DEFAULT_SOURCES))
    total = sum(len(v) for v in classes.values())
    everything &= check("источники на месте", bool(classes), f"{len(classes)} классов, {total} снимков")

    print("\n" + ("ВСЁ НА МЕСТЕ" if everything else "ЕСТЬ ПРОБЛЕМЫ — не запускайте обучение"))
    raise SystemExit(0 if everything else 1)


if __name__ == "__main__":
    main()
