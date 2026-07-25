"""Догружает органику из датасета «Waste Classification (organic / recyclable)».

Органика — самый слабый класс в нашей сборке: Vegetation даёт всего 436 снимков,
и это единственный класс, где RealWaste почти не помогает. Здесь берётся класс
«O» (organic) из третьего источника — 13 тысяч снимков еды и растительных
остатков, снятых в других условиях.

Скачивается parquet целиком, а не по картинке через API: 13 тысяч отдельных
запросов заняли бы часы.

    python -m prediction.fetch_organics
    python -m prediction.fetch_organics --limit 2000

Источник: https://huggingface.co/datasets/bryandts/waste_organic_anorganic_classification
"""

from __future__ import annotations

import argparse
import io
import json
import ssl
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes" / "Food Organics"

DATASET = "bryandts/waste_organic_anorganic_classification"
PARQUET_URL = (
    "https://datasets-server.huggingface.co/parquet"
    f"?dataset={DATASET.replace('/', '%2F')}"
)
#: В датасете две метки: 0 — organic, 1 — recyclable. Нужна только первая.
ORGANIC_LABEL = 0

#: Сколько брать. Больше полутора тысяч смысла нет: органики станет столько же,
#: сколько крупнейших классов, а дальше начнётся перекос в другую сторону.
DEFAULT_LIMIT = 1500


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def main() -> None:
    parser = argparse.ArgumentParser(description="Догрузка органики")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args()

    context = _ssl_context()

    with urllib.request.urlopen(PARQUET_URL, context=context) as response:
        files = json.load(response)["parquet_files"]
    train_files = [f for f in files if f["split"] == "train"]
    if not train_files:
        raise SystemExit("В датасете нет train-части.")

    import pyarrow.parquet as pq

    from prediction.train_classifier import _fingerprint

    TARGET.mkdir(parents=True, exist_ok=True)
    saved = 0

    for entry in train_files:
        if saved >= args.limit:
            break
        size_mb = entry["size"] / 1048576
        print(f"Скачиваем {entry['filename']} ({size_mb:.0f} МБ)…")
        with urllib.request.urlopen(entry["url"], context=context) as response:
            raw = response.read()

        table = pq.read_table(io.BytesIO(raw))
        labels = table.column("label").to_pylist()
        images = table.column("image").to_pylist()

        for index, (label, image) in enumerate(zip(labels, images)):
            if saved >= args.limit:
                break
            if label != ORGANIC_LABEL:
                continue

            data = image.get("bytes") if isinstance(image, dict) else None
            if not data:
                continue

            path = TARGET / f"organic_{index}.jpg"
            path.write_bytes(data)
            try:
                _fingerprint(path)  # проверяем, что файл читается как картинка
            except Exception:  # noqa: BLE001
                path.unlink(missing_ok=True)
                continue
            saved += 1

    print(f"Сохранено в {TARGET.relative_to(PROJECT_ROOT)}: {saved} снимков органики")


if __name__ == "__main__":
    main()
