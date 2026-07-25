"""Готовит картинки для справочника — по одной на категорию.

В дизайне под каждым типом отхода было место под фото, но самих фотографий
не было: стояли пустые слоты с подписью. Здесь они заполняются реальными
снимками из наших же датасетов — тех самых, на которых учится модель.

Берётся снимок из «своего» класса, обрезается по центру в квадрат и ужимается:
в справочнике картинка показывается небольшой, хранить оригиналы незачем.

    python -m prediction.build_guide_images

Важно про лицензии: RealWaste распространяется под CC BY-NC-SA 4.0 —
некоммерческое использование с указанием источника. Для показа в приложении
этого достаточно, но перед коммерческим запуском снимки нужно заменить
на свои или купленные.
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "app" / "static" / "guide"

#: Категория справочника → классы датасета, из которых берём снимок.
#: Порядок важен: первый класс, где нашлись снимки, и будет источником.
CATEGORY_SOURCES: dict[str, list[str]] = {
    "plastic": ["Plastic"],
    "glass": ["Glass"],
    "paper": ["Cardboard", "Paper"],
    "metal": ["Metal"],
    "organic": ["Food Organics", "Vegetation"],
    "special": ["Battery"],
    "other": ["Textile Trash", "Miscellaneous Trash"],
}

SIZE = 640
SEED = 42


def pick_image(classes: list[str], images_by_class: dict[str, list[Path]]) -> Path | None:
    """Выбирает снимок детерминированно: перезапуск не меняет картинки."""
    rng = random.Random(SEED)
    for class_name in classes:
        images = images_by_class.get(class_name) or []
        if images:
            return rng.choice(sorted(images))
    return None


def prepare(source: Path, destination: Path) -> None:
    """Квадратная обрезка по центру и уменьшение до SIZE."""
    from PIL import Image

    with Image.open(source) as image:
        image = image.convert("RGB")
        side = min(image.size)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        image = image.crop((left, top, left + side, top + side))
        image = image.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
        image.save(destination, "JPEG", quality=82, optimize=True)


def main() -> None:
    from prediction.train_classifier import DEFAULT_SOURCES, collect_classes

    images_by_class = collect_classes(DEFAULT_SOURCES)
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True, exist_ok=True)

    missing: list[str] = []
    for category, classes in CATEGORY_SOURCES.items():
        source = pick_image(classes, images_by_class)
        if source is None:
            missing.append(category)
            continue
        destination = TARGET / f"{category}.jpg"
        prepare(source, destination)
        size_kb = destination.stat().st_size / 1024
        print(f"  {category:10} ← {source.parent.name:22} {size_kb:.0f} КБ")

    if missing:
        print(f"\nБез картинки остались: {', '.join(missing)} — нет снимков в датасетах.")
    print(f"\nГотово: {TARGET.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
