"""Дополняет независимый тест органикой и текстилем.

Основной тест собран из `dmedhi/garbage-image-classification-detection`, а там
только пять «материальных» классов. Из-за этого три категории справочника
из семи не измерялись вообще: про органику, особые отходы и прочее мы знали
лишь цифры валидации, а они завышены — валидация показывала 97% при 91%
на независимом тесте.

Первым кандидатом был `shravya11/garbage-dataset`: десять классов, включая
battery, biological, clothes, shoes. Проверка отпечатков показала, что это
зеркало того же Kaggle-набора, на котором мы учились, — двенадцать
из двенадцати снимков совпали до пикселя. Мерить на нём значит спрашивать
модель то, что она уже видела.

Поэтому источники здесь — из совсем другой области:

* органика — `Voxel51/food-waste-dataset`, пищевые отходы в лотках и баках;
* прочее — `Cleanlab/footwear-demo`, обувь (по справочнику это «прочее»:
  подошва, ткань и клей неразделимы).

Батареек независимого источника найти не удалось: всё, что есть на HuggingFace
под этой меткой, — либо телеметрия аккумуляторов, либо копии того же
garbage-набора. Значит, «особые отходы» остаются неизмеренными, и говорить
про их точность мы права не имеем.

    python -m prediction.extend_testset
    python -m prediction.extend_testset --per-class 150

Каждый снимок сверяется с отпечатками обучающей выборки — и точным,
и перцептивным, — чтобы в тест не попало то, на чём учились.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import io
import json
import ssl
import threading
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "testset"

ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100

#: Откуда что берём. `label` — какие метки исходного датасета годятся;
#: None означает «весь датасет целиком относится к нашему классу».
SOURCES = [
    {
        "dataset": "Voxel51/food-waste-dataset",
        "target": "Food Organics",
        "labels": None,
    },
    {
        "dataset": "Cleanlab/footwear-demo",
        "target": "Textile Trash",
        "labels": None,
    },
]

PER_CLASS = 150
#: Десять ядер, но упираемся не в них, а в ожидание сети. Больше двух десятков
#: потоков HuggingFace начинает притормаживать сам.
THREADS = 16


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def _get_json(context: ssl.SSLContext, url: str) -> dict:
    with urllib.request.urlopen(url, context=context) as response:
        return json.load(response)


def splits_of(context: ssl.SSLContext, dataset: str) -> list[tuple[str, str]]:
    url = "https://datasets-server.huggingface.co/splits?dataset=" + urllib.parse.quote(
        dataset, safe=""
    )
    return [(s["config"], s["split"]) for s in _get_json(context, url)["splits"]]


def image_urls(
    context: ssl.SSLContext, dataset: str, labels: set[str] | None, limit: int
) -> list[str]:
    """Ссылки на снимки датасета. Идём по страницам, пока не наберём limit."""
    found: list[str] = []
    for config, split in splits_of(context, dataset):
        offset = 0
        while len(found) < limit:
            url = (
                f"{ROWS_URL}?dataset={urllib.parse.quote(dataset, safe='')}"
                f"&config={urllib.parse.quote(config, safe='')}"
                f"&split={urllib.parse.quote(split, safe='')}"
                f"&offset={offset}&length={PAGE}"
            )
            try:
                payload = _get_json(context, url)
            except Exception:  # noqa: BLE001
                break

            rows = payload.get("rows", [])
            if not rows:
                break

            names = None
            if labels:
                for feature in payload.get("features", []):
                    if feature["type"].get("_type") == "ClassLabel":
                        names = (feature["name"], feature["type"]["names"])
                        break

            for row in rows:
                item = row["row"]
                if labels and names:
                    field, mapping = names
                    if mapping[item[field]] not in labels:
                        continue
                picture = item.get("image")
                src = picture.get("src") if isinstance(picture, dict) else None
                if src:
                    found.append(src)
                if len(found) >= limit:
                    break
            offset += PAGE
    return found


def training_fingerprints() -> set[str]:
    """Перцептивные отпечатки всего, на чём модель училась."""
    from prediction.train_classifier import _fingerprint

    suffixes = {".jpg", ".jpeg", ".png", ".webp"}
    paths = [
        path
        for root in ("RealWaste", "extra-classes")
        if (PROJECT_ROOT / root).exists()
        for path in (PROJECT_ROOT / root).rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    ]

    prints: set[str] = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=THREADS) as pool:
        for result in pool.map(_safe_fingerprint, paths):
            if result:
                prints.add(result)
    return prints


def _safe_fingerprint(path: Path) -> str | None:
    from prediction.train_classifier import _fingerprint

    try:
        return _fingerprint(path)[1]
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Расширение независимого теста")
    parser.add_argument("--per-class", type=int, default=PER_CLASS)
    parser.add_argument("--threads", type=int, default=THREADS)
    args = parser.parse_args()

    context = _ssl_context()

    print("Считаем отпечатки обучающей выборки…")
    known = training_fingerprints()
    print(f"  {len(known)} снимков в обучении\n")

    from PIL import Image

    from prediction.train_classifier import _fingerprint

    for source in SOURCES:
        target_class = source["target"]
        directory = TARGET / target_class
        directory.mkdir(parents=True, exist_ok=True)

        # Запас втрое: часть отсеется дедупликацией и битыми ссылками.
        urls = image_urls(context, source["dataset"], source["labels"], args.per_class * 3)
        print(f"{source['dataset']:<34} → {target_class:<16} ссылок {len(urls)}")

        lock = threading.Lock()
        saved = 0
        overlap = 0

        def fetch(pair: tuple[int, str]) -> None:
            nonlocal saved, overlap
            index, url = pair
            with lock:
                if saved >= args.per_class:
                    return

            path = directory / f"extra_{index:04d}.jpg"
            try:
                with urllib.request.urlopen(url, context=context) as response:
                    data = response.read()
                with Image.open(io.BytesIO(data)) as picture:
                    picture = picture.convert("RGB")
                    picture.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                    picture.save(path, "JPEG", quality=90)
                fingerprint = _fingerprint(path)[1]
            except Exception:  # noqa: BLE001
                path.unlink(missing_ok=True)
                return

            with lock:
                if fingerprint in known or saved >= args.per_class:
                    path.unlink(missing_ok=True)
                    overlap += fingerprint in known
                    return
                known.add(fingerprint)  # снимок мог повториться внутри датасета
                saved += 1

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as pool:
            list(pool.map(fetch, enumerate(urls)))

        print(f"  добавлено {saved}, отброшено как уже виденное {overlap}\n")

    print("Состав теста:")
    for directory in sorted(TARGET.iterdir()):
        if directory.is_dir():
            print(f"  {directory.name:<16} {sum(1 for _ in directory.iterdir())}")


if __name__ == "__main__":
    main()
