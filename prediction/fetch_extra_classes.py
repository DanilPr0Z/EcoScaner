"""Догружает снимки из второго датасета в extra-classes/.

Зачем второй источник. RealWaste снят в одних условиях — предметы лежат на
конвейере полигона. Модель, обученная только на нём, цепляется за фон и оттенок
и путается на бытовых фото: матовая стеклянная бутылка на офисном столе
уезжала в «бумагу». Второй датасет снят совсем иначе — предметы на белом фоне,
студийный свет. Одна и та же категория в двух разных доменах не даёт модели
опереться на цвет.

Плюс здесь есть батарейки: особых отходов в RealWaste нет вовсе, и без этого
источника категория была недостижима.

Классы внешнего датасета раскладываются под именами классов RealWaste —
скрипт обучения объединяет одноимённые папки из обоих источников.

    python -m prediction.fetch_extra_classes

Источник: https://huggingface.co/datasets/UdaraChamidu/Garbage-Classification-with-12-classes
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes"

ARCHIVE_URL = (
    "https://huggingface.co/datasets/UdaraChamidu/"
    "Garbage-Classification-with-12-classes/resolve/main/garbage_classification.zip"
)
ARCHIVE_ROOT = "garbage_classification"

#: Класс внешнего датасета → (класс в нашей раскладке, сколько снимков брать).
#: Ограничение нужно там, где класс несоразмерно велик: одежды и обуви в
#: источнике 7300 снимков, и без потолка они перевесили бы «прочее» целиком.
MAPPING: dict[str, tuple[str, int | None]] = {
    "battery": ("Battery", None),
    "biological": ("Food Organics", None),
    "brown-glass": ("Glass", None),
    "green-glass": ("Glass", None),
    "white-glass": ("Glass", None),
    "cardboard": ("Cardboard", None),
    "paper": ("Paper", None),
    "metal": ("Metal", None),
    "plastic": ("Plastic", None),
    "clothes": ("Textile Trash", 900),
    "shoes": ("Textile Trash", 700),
    "trash": ("Miscellaneous Trash", None),
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def download(destination: Path) -> None:
    print(f"Скачиваем датасет (~240 МБ)…")
    with urllib.request.urlopen(ARCHIVE_URL) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)
    print(f"Готово: {destination.stat().st_size / 1024 / 1024:.0f} МБ")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / "garbage.zip"
        download(archive)

        print("Распаковываем…")
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp_dir)

        source_root = tmp_dir / ARCHIVE_ROOT
        counts: dict[str, int] = {}

        for source_name, (target_name, limit) in MAPPING.items():
            source_dir = source_root / source_name
            if not source_dir.is_dir():
                print(f"  пропускаем {source_name}: нет в архиве")
                continue

            images = sorted(
                p for p in source_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
            )
            if limit is not None:
                images = images[:limit]

            target_dir = TARGET / target_name
            target_dir.mkdir(parents=True, exist_ok=True)
            for image in images:
                # Имя источника в префиксе: классы из разных папок сливаются
                # в одну, и одинаковые имена файлов затёрли бы друг друга.
                shutil.copy2(image, target_dir / f"{source_name}_{image.name}")

            counts[target_name] = counts.get(target_name, 0) + len(images)
            print(f"  {source_name:14} → {target_name:20} {len(images):5}")

    print(f"\nИтого в {TARGET.name}/:")
    for name, count in sorted(counts.items()):
        print(f"  {name:20} {count:5}")
    print(f"  всего {sum(counts.values())}")


if __name__ == "__main__":
    main()
