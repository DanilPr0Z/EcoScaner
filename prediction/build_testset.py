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
#: Берём обе части. Мы на этом датасете не учились вообще, поэтому его train
#: для нас такие же незнакомые снимки, как и validation. А маленькая выборка
#: ничего не меряет: на 27 снимках доверительный интервал точности 63–92%,
#: и разница в один кадр выглядит как «просадка на 4 пункта».
SPLITS = ("validation", "train")
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100

#: Класс третьего датасета → класс нашей раскладки.
#:
#: «Garbage» пропускаем: это свалка целиком, а не отдельный предмет.
#:
#: «Trash» тоже пропускаем, и это важнее. У нас «прочее» — вещи из смешанных
#: неразделимых материалов, а там это корзина для любого мусора, снятого
#: на земле. При проверке выяснилось: под меткой «Trash» лежат полиэтиленовый
#: пакет и фольгированная форма для запекания. Модель называет их пластиком
#: и металлом — и по нашему справочнику она права, а метка неверна. Считать
#: такие случаи ошибками значит занижать оценку и, что хуже, чинить то,
#: что не сломано.
CLASS_MAP = {
    "Glass": "Glass",
    "Metal": "Metal",
    "Plastic": "Plastic",
    "Paper": "Paper",
    "Cardboard": "Cardboard",
}

#: Сколько снимков на класс. Меньше сотни — и доверительный интервал точности
#: становится шире, чем разница между версиями модели.
PER_CLASS = 150


def fetch_rows(limit: int) -> list[dict]:
    rows: list[dict] = []
    for split in SPLITS:
        offset = 0
        base = f"{ROWS_URL}?dataset={DATASET.replace('/', '%2F')}&config=default&split={split}"
        while len(rows) < limit:
            url = f"{base}&offset={offset}&length={PAGE}"
            with urllib.request.urlopen(url, context=SSL_CONTEXT) as response:
                payload = json.load(response)
            batch = payload.get("rows", [])
            if not batch:
                break
            for row in batch:
                row["_split"] = split
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

    print(f"Скачиваем {' и '.join(SPLITS)} третьего датасета…")
    rows = fetch_rows(PER_CLASS * len(CLASS_MAP) * 4)
    print(f"  получено строк: {len(rows)}")

    from prediction.train_classifier import _fingerprint

    saved: dict[str, int] = {}
    overlapped = 0

    for row in rows:
        data = row.get("row", {})
        data["_split"] = row.get("_split", "s")
        source_class = data.get("class_name")
        target_class = CLASS_MAP.get(source_class)
        if not target_class or saved.get(target_class, 0) >= PER_CLASS:
            continue

        url = (data.get("image") or {}).get("src")
        if not url:
            continue

        target_dir = TARGET / target_class
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{data.get('_split', 's')}_{row.get('row_idx')}.jpg"

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
