"""Все модели на одной и той же текущей валидации.

    python -m prediction.compare_on_val

Нужен, потому что потери разных прогонов сравнивать нельзя, если между ними
менялась выборка. Сравнивать можно только модели — на одних данных.

Прежняя модель показывала потери 0.14, новая 0.24 — но мерились они на разных
выборках: в валидацию с тех пор вошли уличные снимки TACO и бытовые Open Images.
Сравнивать такие числа нельзя, можно только пересчитать старую модель на новых.

Читаем через PIL и собственные преобразования модели: класс датасета ultralytics
ходит в OpenCV и спотыкается на отдельных файлах, а нам нужна не его логика,
а ровно то же преобразование, что применяется при распознавании.
"""
import pathlib, sys
sys.path.insert(0, "/Users/danil/PycharmProjects/Xakaton")
import torch, torch.nn.functional as F
from PIL import Image
from ultralytics import YOLO
from ultralytics.data.augment import classify_transforms

ROOT = pathlib.Path("/Users/danil/PycharmProjects/Xakaton")
VAL = ROOT / "datasets" / "realwaste" / "val"
CLASSES = sorted(p.name for p in VAL.iterdir() if p.is_dir())


def measure(weights: str, imgsz: int):
    model = YOLO(str(ROOT / weights))
    net = model.model.eval().float()
    transform = classify_transforms(size=imgsz)
    total = hits = seen = 0.0
    batch, labels = [], []

    def flush():
        nonlocal total, hits, seen, batch, labels
        if not batch:
            return
        x = torch.stack(batch)
        y = torch.tensor(labels)
        with torch.no_grad():
            out = net(x)
            out = out[1] if isinstance(out, (list, tuple)) else out
        total += float(F.cross_entropy(out, y, reduction="sum"))
        hits += int((out.argmax(1) == y).sum())
        seen += len(y)
        batch, labels = [], []

    for index, name in enumerate(CLASSES):
        for path in sorted((VAL / name).iterdir()):
            try:
                with Image.open(path) as im:
                    batch.append(transform(im.convert("RGB")))
            except Exception:  # noqa: BLE001 - битый файл пропускаем
                continue
            labels.append(index)
            if len(batch) == 32:
                flush()
    flush()
    return total / seen, hits / seen, int(seen)


print(f"{'модель':<34}{'val_loss':>11}{'точность':>11}{'снимков':>10}")
print("-" * 66)
for weights, size, label in (
    ("prediction/waste_classifier.pt", 224, "боевая (стоит на сервере)"),
    ("prediction/waste_classifier.s.pt", 224, "8s + уличные снимки"),
    ("prediction/waste_classifier.m288.pt", 288, "новая 8m на 288"),
):
    loss, acc, n = measure(weights, size)
    print(f"{label:<34}{loss:>11.4f}{acc:>11.2%}{n:>10}")
print("\nВсе — на одной и той же нынешней валидации, сглаживание не применяется.")
