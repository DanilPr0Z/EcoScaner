"""Догружает бытовые снимки из Open Images — под путаницу стекла и металла.

Живой случай с сервера: гранёный стеклянный стакан на тёмной решётке
определился металлом с уверенностью 89%. В независимом тесте пара есть в обе
стороны — `стекло → металл` 4 ошибки, `металл → стекло` 11. Модель путает
блестящие цилиндры: вертикальные рёбра дают полосы бликов, и на 224 пикселях
это неотличимо от гофрированной банки.

Студийными данными это не лечится: там бутылки на белом фоне, а не стакан
на кухонном столе. Open Images — обычные любительские фотографии, то есть
ровно тот домен, в котором снимает пользователь.

Датасет целиком не скачать (513 ГБ один train), поэтому берём только нужное:
разметка отдаётся отдельным CSV, а снимки — поштучно из открытого бакета.

    python -m prediction.fetch_openimages
    python -m prediction.fetch_openimages --per-class 400 --splits validation test train

Предмет должен занимать заметную часть кадра, иначе метка на весь кадр
научит модель решать по фону — тому самому, от чего мы её лечим. И кадр
отбрасывается, если на нём есть предмет другого нашего класса: бутылка рядом
с банкой не даёт понять, что тут главное.

Источник: https://storage.googleapis.com/openimages/v5/
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import csv
import io
import ssl
import threading
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes"
CACHE = PROJECT_ROOT / ".cache" / "openimages"

#: У train разметка лежит в другом наборе и под другим именем — в v5 его просто
#: нет, и адрес по общему шаблону отдаёт 403.
ANNOTATIONS = {
    "validation": "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv",
    "test": "https://storage.googleapis.com/openimages/v5/test-annotations-bbox.csv",
    "train": "https://storage.googleapis.com/openimages/v6/oidv6-train-annotations-bbox.csv",
}
IMAGE_URL = "https://open-images-dataset.s3.amazonaws.com/{split}/{image_id}.jpg"

#: Код класса Open Images → класс нашей раскладки.
#:
#: Берём только то, что справочник трактует однозначно. «Bottle» пропускаем
#: намеренно, хотя снимков там больше всего: бутылка бывает и стеклянной,
#: и пластиковой, а разметка материал не различает — мы бы учили модель
#: на заведомо перепутанных метках. По той же причине мимо идут «Coffee cup»
#: (бумажный или керамический) и «Box» (картон или пластик).
OPEN_IMAGES_CLASSES = {
    "/m/09tvcd": "Glass",     # Wine glass — прозрачное стекло с бликами
    "/m/02jnhm": "Metal",     # Tin can — вторая половина той же путаницы
    "/m/05gqfk": "Plastic",   # Plastic bag
    "/m/02w3r3": "Paper",     # Paper towel
    "/m/09gtd": "Paper",      # Toilet paper
}

#: Какую долю кадра должен занимать предмет. Меньше — и метка на весь кадр
#: становится меткой на фон.
MIN_AREA = 0.12

DEFAULT_PER_CLASS = 400
THREADS = 16


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def annotations(context: ssl.SSLContext, split: str) -> Path:
    """CSV разметки, с кэшем: train весит больше гигабайта."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{split}-annotations-bbox.csv"
    if path.exists():
        return path

    url = ANNOTATIONS.get(split)
    if not url:
        raise SystemExit(f"Неизвестная часть датасета: {split}")
    print(f"  качаем разметку {split} (у train это 2.1 ГБ)…")
    with urllib.request.urlopen(url, context=context) as response:
        path.write_bytes(response.read())
    return path


def pick_images(path: Path) -> dict[str, str]:
    """Снимки, годные для обучения: {идентификатор: наш класс}.

    Кадр берём, если предмет одного из наших классов занимает заметную долю
    и на кадре нет предмета другого нашего класса.
    """
    largest: dict[str, dict[str, float]] = collections.defaultdict(dict)

    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            target = OPEN_IMAGES_CLASSES.get(row["LabelName"])
            if target is None:
                continue
            area = (float(row["XMax"]) - float(row["XMin"])) * (
                float(row["YMax"]) - float(row["YMin"])
            )
            image_id = row["ImageID"]
            if area > largest[image_id].get(target, 0.0):
                largest[image_id][target] = area

    chosen: dict[str, str] = {}
    for image_id, areas in largest.items():
        if len(areas) != 1:
            continue  # на кадре два наших класса — непонятно, что главное
        target, area = next(iter(areas.items()))
        if area >= MIN_AREA:
            chosen[image_id] = target
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description="Догрузка Open Images")
    parser.add_argument("--per-class", type=int, default=DEFAULT_PER_CLASS)
    parser.add_argument("--splits", nargs="+", default=["validation", "test"])
    parser.add_argument("--threads", type=int, default=THREADS)
    args = parser.parse_args()

    context = _ssl_context()

    from PIL import Image

    from prediction.train_classifier import _fingerprint

    saved: collections.Counter[str] = collections.Counter()
    lock = threading.Lock()

    for split in args.splits:
        chosen = pick_images(annotations(context, split))
        counts = collections.Counter(chosen.values())
        print(f"{split}: годных кадров {len(chosen)} — " +
              ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))

        def fetch(item: tuple[str, str]) -> None:
            image_id, target = item
            with lock:
                if saved[target] >= args.per_class:
                    return

            directory = TARGET / target
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"oi_{image_id}.jpg"
            if path.exists():
                return

            try:
                url = IMAGE_URL.format(split=split, image_id=image_id)
                with urllib.request.urlopen(url, context=context, timeout=30) as response:
                    data = response.read()
                with Image.open(io.BytesIO(data)) as picture:
                    picture = picture.convert("RGB")
                    picture.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                    picture.save(path, "JPEG", quality=88)
                _fingerprint(path)
            except Exception:  # noqa: BLE001
                path.unlink(missing_ok=True)
                return

            with lock:
                if saved[target] >= args.per_class:
                    path.unlink(missing_ok=True)
                    return
                saved[target] += 1

        # Перемешивать незачем: идентификаторы и так в случайном порядке,
        # а сортировка по классу дала бы перекос по источнику съёмки.
        items = [(k, v) for k, v in chosen.items() if saved[v] < args.per_class]
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as pool:
            list(pool.map(fetch, items))

        print("  добавлено: " + ", ".join(f"{k} {v}" for k, v in sorted(saved.items())))

    print("\nИтого добавлено:")
    for name, count in sorted(saved.items()):
        print(f"  {name:12} {count}")


if __name__ == "__main__":
    main()
