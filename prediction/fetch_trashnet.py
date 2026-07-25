"""Догружает TrashNet — снимки отходов на белом фоне.

Зачем именно он. Модель путает белые матовые цилиндры: алюминиевую банку
называет пластиком, бумажный стакан — металлом. Все три материала в этой форме
выглядят одинаково, а различает их фактура поверхности и блики — то, чему
можно научить только на разнообразных примерах.

TrashNet снят в четвёртом, отличном от наших источников виде: один предмет
на белом фоне, студийный свет, крупно. Ровно те кадры, где материал видно
по поверхности, а не по окружению.

    python -m prediction.fetch_trashnet
    python -m prediction.fetch_trashnet --per-class 400

Класс «trash» не берём: как и в другом датасете, это корзина для всего подряд,
и её метки расходятся с нашим справочником.

Источник: https://huggingface.co/datasets/garythung/trashnet
"""

from __future__ import annotations

import argparse
import io
import json
import ssl
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes"

DATASET = "garythung/trashnet"
PARQUET_URL = (
    "https://datasets-server.huggingface.co/parquet"
    f"?dataset={DATASET.replace('/', '%2F')}"
)

#: Метка TrashNet → класс нашей раскладки. Порядок как в ClassLabel датасета.
LABELS = ["cardboard", "glass", "metal", "paper", "plastic", "trash"]
CLASS_MAP = {
    "cardboard": "Cardboard",
    "glass": "Glass",
    "metal": "Metal",
    "paper": "Paper",
    "plastic": "Plastic",
}

#: Сколько брать на класс. Датасет на HuggingFace вдвое больше оригинального
#: TrashNet — значит, содержит производные копии. Их отсеет дедупликация,
#: но качать 3.5 ГБ ради этого незачем.
DEFAULT_PER_CLASS = 600


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def main() -> None:
    parser = argparse.ArgumentParser(description="Догрузка TrashNet")
    parser.add_argument("--per-class", type=int, default=DEFAULT_PER_CLASS)
    args = parser.parse_args()

    context = _ssl_context()
    with urllib.request.urlopen(PARQUET_URL, context=context) as response:
        files = [f for f in json.load(response)["parquet_files"] if f["split"] == "train"]

    # Мелкие части идут первыми, и это не только про скорость: в них лежат
    # оригинальные снимки TrashNet, а полуторагигабайтные части — раздутые
    # производные того же самого. Тридцати мегабайт хватает почти на весь
    # исходный датасет.
    files.sort(key=lambda f: f["size"])

    import pyarrow.parquet as pq

    from prediction.train_classifier import _fingerprint

    saved: dict[str, int] = {}
    seen: set[str] = set()

    for entry in files:
        if all(saved.get(c, 0) >= args.per_class for c in CLASS_MAP.values()):
            print("Набрали нужное количество, остальные части не качаем.")
            break

        print(f"Скачиваем {entry['filename']} ({entry['size'] / 1048576:.0f} МБ)…")
        with urllib.request.urlopen(entry["url"], context=context) as response:
            raw = response.read()

        table = pq.read_table(io.BytesIO(raw))
        labels = table.column("label").to_pylist()
        images = table.column("image").to_pylist()

        for index, (label, image) in enumerate(zip(labels, images)):
            name = LABELS[label] if isinstance(label, int) else str(label)
            target_class = CLASS_MAP.get(name)
            if target_class is None or saved.get(target_class, 0) >= args.per_class:
                continue

            data = image.get("bytes") if isinstance(image, dict) else None
            if not data:
                continue

            directory = TARGET / target_class
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"trashnet_{name}_{index}.jpg"
            path.write_bytes(data)

            try:
                fingerprint = _fingerprint(path)[1]
            except Exception:  # noqa: BLE001
                path.unlink(missing_ok=True)
                continue

            # Внутри самого датасета много производных копий одного кадра —
            # берём по одному представителю, иначе выборка раздуется впустую.
            if fingerprint in seen:
                path.unlink(missing_ok=True)
                continue
            seen.add(fingerprint)
            saved[target_class] = saved.get(target_class, 0) + 1

    print("\nДобавлено:")
    for name, count in sorted(saved.items()):
        print(f"  {name:22} {count}")
    print(f"  всего {sum(saved.values())}")


if __name__ == "__main__":
    main()
