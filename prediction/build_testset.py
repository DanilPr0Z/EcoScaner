"""Собирает независимый тестовый набор из третьего источника.

Зачем он нужен. Валидационная выборка нарезана из тех же датасетов, на которых
модель училась: те же камеры, тот же фон, та же манера съёмки. Высокая точность
на ней говорит лишь о том, что модель выучила эти датасеты, а не о том, что она
работает на обычных фотографиях. Понять это можно только на снимках, которых
в обучении не было вовсе.

Поэтому берём третий датасет — не тот, на котором учились, — и дополнительно
выбрасываем из него всё, что перцептивно совпадает с обучающими снимками.
Что останется, и есть честная проверка.

    python -m prediction.build_testset

Источник: https://huggingface.co/datasets/dmedhi/garbage-image-classification-detection
"""

from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ssl_context() -> ssl.SSLContext:
    """У python.org-сборки на macOS нет доступа к системным корневым сертификатам,
    поэтому берём набор из certifi — иначе любой https падает на проверке."""
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = _ssl_context()
TARGET = PROJECT_ROOT / "testset"

DATASET = "dmedhi/garbage-image-classification-detection"
SPLIT = "validation"
ROWS_URL = (
    "https://datasets-server.huggingface.co/rows"
    f"?dataset={DATASET.replace('/', '%2F')}&config=default&split={SPLIT}"
)
PAGE = 100

#: Класс третьего датасета → класс нашей раскладки.
#: «Garbage» пропускаем: это свалка целиком, а не отдельный предмет.
CLASS_MAP = {
    "Glass": "Glass",
    "Metal": "Metal",
    "Plastic": "Plastic",
    "Paper": "Paper",
    "Cardboard": "Cardboard",
    "Trash": "Miscellaneous Trash",
}

#: Сколько снимков на класс — на проверку хватает, качать меньше и быстрее.
PER_CLASS = 60


def fetch_rows(limit: int) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while len(rows) < limit:
        with urllib.request.urlopen(f"{ROWS_URL}&offset={offset}&length={PAGE}", context=SSL_CONTEXT) as response:
            payload = json.load(response)
        batch = payload.get("rows", [])
        if not batch:
            break
        rows.extend(batch)
        offset += PAGE
        if offset >= payload.get("num_rows_total", 0):
            break
    return rows


def training_fingerprints() -> set[str]:
    """Перцептивные отпечатки всего, на чём модель училась."""
    from prediction.train_classifier import (
        DEFAULT_SOURCES,
        _fingerprint,
        collect_classes,
    )

    prints: set[str] = set()
    for images in collect_classes(DEFAULT_SOURCES).values():
        for path in images:
            try:
                prints.add(_fingerprint(path)[1])
            except Exception:  # noqa: BLE001
                continue
    return prints


def main() -> None:
    print("Считаем отпечатки обучающих снимков…")
    known = training_fingerprints()
    print(f"  {len(known)} различных кадров в обучении")

    print(f"Скачиваем {SPLIT}-часть третьего датасета…")
    rows = fetch_rows(PER_CLASS * len(CLASS_MAP) * 3)
    print(f"  получено строк: {len(rows)}")

    from prediction.train_classifier import _fingerprint

    saved: dict[str, int] = {}
    overlapped = 0

    for row in rows:
        data = row.get("row", {})
        source_class = data.get("class_name")
        target_class = CLASS_MAP.get(source_class)
        if not target_class or saved.get(target_class, 0) >= PER_CLASS:
            continue

        url = (data.get("image") or {}).get("src")
        if not url:
            continue

        target_dir = TARGET / target_class
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{row.get('row_idx')}.jpg"

        try:
            with urllib.request.urlopen(url, context=SSL_CONTEXT) as response, path.open("wb") as out:
                out.write(response.read())
            # Снимок, который уже был на обучении, проверкой не является.
            if _fingerprint(path)[1] in known:
                path.unlink()
                overlapped += 1
                continue
        except Exception:  # noqa: BLE001
            path.unlink(missing_ok=True)
            continue

        saved[target_class] = saved.get(target_class, 0) + 1

    print(f"\nОтброшено как совпадающее с обучением: {overlapped}")
    print(f"Итого в {TARGET.name}/:")
    for name, count in sorted(saved.items()):
        print(f"  {name:22} {count}")
    print(f"  всего {sum(saved.values())}")


if __name__ == "__main__":
    main()
