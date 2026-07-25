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
import hashlib
import random
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Источники снимков: папка на класс. Одноимённые классы объединяются.
#: RealWaste лежит отдельно от дополнительных классов — у него своя лицензия.
DEFAULT_SOURCES = [
    PROJECT_ROOT / "realwaste-main" / "RealWaste",
    PROJECT_ROOT / "extra-classes",
]
#: Куда раскладывается train/val для ultralytics.
DEFAULT_SPLIT_DIR = PROJECT_ROOT / "datasets" / "realwaste"
#: Куда кладутся веса обученной модели.
DEFAULT_WEIGHTS = PROJECT_ROOT / "prediction" / "waste_classifier.pt"

#: Класс датасета → (категория справочника по-русски, название предмета).
#: Русские названия переводятся в id справочника в app/services/recognition/ml.py.
WASTE_CLASSES_RU: dict[str, tuple[str, str]] = {
    "Cardboard": ("бумага", "картон"),
    "Paper": ("бумага", "бумага"),
    "Glass": ("стекло", "стекло"),
    "Metal": ("металл", "металл"),
    "Plastic": ("пластик", "пластик"),
    "Food Organics": ("органика", "пищевые отходы"),
    "Vegetation": ("органика", "растительные остатки"),
    "Textile Trash": ("прочее", "текстиль"),
    "Miscellaneous Trash": ("прочее", "смешанные отходы"),
    # Особых отходов в RealWaste нет — класс приходит из extra-classes/.
    "Battery": ("особые отходы", "батарейка"),
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

#: Аугментация. Главное здесь — сильный разброс насыщенности и яркости:
#: без него модель приучается решать по цвету, и матовая белая бутылка уезжает
#: в «бумагу» просто потому, что светлая. Когда цвет на каждой эпохе разный,
#: опереться остаётся только на форму и фактуру.
#: Повороты, сдвиги и случайное затирание добавляют устойчивости к ракурсу
#: и к тому, что предмет снят не целиком.
AUGMENTATION = {
    "hsv_h": 0.05,
    "hsv_s": 0.9,
    "hsv_v": 0.5,
    "degrees": 20.0,
    "translate": 0.15,
    "scale": 0.6,
    "fliplr": 0.5,
    "erasing": 0.4,
}


def collect_classes(sources: list[Path]) -> dict[str, list[Path]]:
    """Собирает снимки по классам из всех источников.

    Одноимённые классы в разных источниках объединяются — так дополнительный
    класс можно положить рядом, не трогая исходный датасет.
    """
    classes: dict[str, list[Path]] = {}
    missing = [s for s in sources if not s.is_dir()]
    if len(missing) == len(sources):
        raise SystemExit(
            "Не найден ни один источник снимков: "
            + ", ".join(str(s) for s in sources)
            + "\nСкачайте RealWaste и положите в realwaste-main/RealWaste."
        )

    for source in sources:
        if not source.is_dir():
            continue
        for class_dir in sorted(p for p in source.iterdir() if p.is_dir()):
            images = [
                p for p in sorted(class_dir.iterdir())
                if p.suffix.lower() in IMAGE_SUFFIXES
            ]
            if images:
                classes.setdefault(class_dir.name, []).extend(images)
    return classes


def _fingerprint(path: Path) -> tuple[str, str]:
    """Отпечатки снимка: точный (по содержимому) и перцептивный (по картинке).

    Перцептивный ловит копии, пережатые или слегка изменённые: во внешнем
    датасете такие есть — часть снимков получена аугментацией исходных.
    """
    from PIL import Image

    data = path.read_bytes()
    exact = hashlib.md5(data).hexdigest()

    # 16×16 полутонов: достаточно подробно, чтобы не склеивать разные предметы.
    with Image.open(path) as im:
        small = im.convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    perceptual = "".join("1" if p > mean else "0" for p in pixels)
    return exact, perceptual


def group_duplicates(images: list[Path]) -> list[list[Path]]:
    """Объединяет копии одного снимка в группы, точные дубликаты выбрасывает.

    Группа целиком уезжает либо в train, либо в val. Если копии одного кадра
    разъедутся по разные стороны, валидационная точность окажется завышенной:
    модель будет отвечать на то, что уже видела на обучении.
    """
    seen_exact: set[str] = set()
    groups: dict[str, list[Path]] = {}

    for path in images:
        try:
            exact, perceptual = _fingerprint(path)
        except Exception:  # noqa: BLE001 - битый файл просто пропускаем
            continue
        if exact in seen_exact:
            continue
        seen_exact.add(exact)
        groups.setdefault(perceptual, []).append(path)

    return list(groups.values())


def build_split(
    sources: list[Path], target: Path, val_share: float, seed: int
) -> dict[str, int]:
    """Раскладывает снимки на train/val симлинками.

    Симлинки, а не копии: датасеты весят сотни мегабайт, дублировать их незачем.
    Разбиение детерминировано seed — повторный запуск даёт тот же split,
    иначе метрики между запусками несравнимы.

    Делим не отдельные снимки, а группы копий — см. group_duplicates.
    """
    classes = collect_classes(sources)
    if not classes:
        raise SystemExit("В источниках не нашлось изображений.")

    if target.exists():
        shutil.rmtree(target)

    counts: dict[str, int] = {}
    dropped = 0
    rng = random.Random(seed)

    for class_name, images in sorted(classes.items()):
        groups = group_duplicates(sorted(images))
        dropped += len(images) - sum(len(g) for g in groups)

        rng.shuffle(groups)
        cut = max(1, round(len(groups) * val_share))
        parts = {"val": groups[:cut], "train": groups[cut:]}

        kept = 0
        for split, split_groups in parts.items():
            split_dir = target / split / class_name
            split_dir.mkdir(parents=True, exist_ok=True)
            for group in split_groups:
                for image in group:
                    (split_dir / image.name).symlink_to(image.resolve())
                    kept += 1

        counts[class_name] = kept

    if dropped:
        print(f"Выброшено точных дубликатов: {dropped}")
    return counts


def attach_progress(model, run_dir: Path, every: int = 5) -> None:
    """Пишет ход обучения в progress.json после каждых нескольких батчей.

    results.csv обновляется раз в эпоху, а эпоха идёт минуты — по нему не понять,
    туда ли всё движется. Здесь пишется бегущее среднее лосса по батчам текущей
    эпохи: если оно падает, направление верное, ждать конца эпохи не нужно.

    Пишем через временный файл: читатель не должен наткнуться на половину записи.
    """
    import json

    state = {"batch": 0}
    target = run_dir / "progress.json"

    def on_epoch_start(trainer) -> None:  # noqa: ANN001
        state["batch"] = 0

    def on_batch_end(trainer) -> None:  # noqa: ANN001
        state["batch"] += 1
        if state["batch"] % every and state["batch"] != 1:
            return

        losses = getattr(trainer, "tloss", None)
        if isinstance(losses, dict):
            loss = float(sum(float(v) for v in losses.values()))
        elif losses is not None:
            loss = float(losses)
        else:
            return

        payload = {
            "epoch": int(trainer.epoch) + 1,
            "epochs": int(trainer.epochs),
            "batch": state["batch"],
            "batches": len(trainer.train_loader),
            # Среднее по всем батчам эпохи, а не по последнему: отдельный батч
            "meanLoss": round(loss, 4),  # скачет и о направлении ничего не говорит.
        }
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            pass  # прогресс — вещь необязательная, ронять из-за него обучение незачем

    def on_train_end(trainer) -> None:  # noqa: ANN001
        target.unlink(missing_ok=True)

    model.add_callback("on_train_epoch_start", on_epoch_start)
    model.add_callback("on_train_batch_end", on_batch_end)
    model.add_callback("on_train_end", on_train_end)


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение классификатора отходов на RealWaste")
    parser.add_argument(
        "--source", type=Path, nargs="+", default=DEFAULT_SOURCES,
        help="папки с классами (одноимённые классы объединяются)",
    )
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
    counts = build_split(list(args.source), args.split_dir, args.val_share, args.seed)
    total = sum(counts.values())
    print(f"Классов: {len(counts)}, снимков: {total}")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        category, obj = WASTE_CLASSES_RU.get(name, ("?", "?"))
        print(f"  {name:22} {count:5}  → {category} / {obj}")

    unmapped = set(counts) - set(WASTE_CLASSES_RU)
    if unmapped:
        raise SystemExit(
            f"В датасете есть классы без соответствия категории: {sorted(unmapped)}. "
            "Добавьте их в WASTE_CLASSES_RU."
        )

    device = args.device or pick_device()
    print(f"\nОбучаем {args.model} на {device}, {args.epochs} эпох, {args.imgsz}px…\n")

    from ultralytics import YOLO

    model = YOLO(args.model)
    attach_progress(model, PROJECT_ROOT / "runs" / "realwaste")
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
        **AUGMENTATION,
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
