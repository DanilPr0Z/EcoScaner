"""Таблицы классов моделей должны сходиться со справочником.

Тест не требует ultralytics и torch: и `ml.py`, и модули моделей импортируют
их лениво, внутри функций. Поэтому рассинхрон ловится в обычном прогоне,
а не когда кто-то запустит сервер с CLASSIFIER=ml.
"""

from __future__ import annotations

from app.data.seed_data import CATEGORIES
from app.services.recognition.ml import (
    _CATEGORY_ID_BY_RU,
    CLASS_TO_CATEGORY,
    COCO_ID_TO_CATEGORY,
)

CATEGORY_IDS = {category["id"] for category in CATEGORIES}


def test_category_translation_covers_guide() -> None:
    """Каждой категории справочника соответствует русское название из моделей."""
    assert set(_CATEGORY_ID_BY_RU.values()) == CATEGORY_IDS


def test_realwaste_classes_map_to_existing_categories() -> None:
    assert CLASS_TO_CATEGORY, "таблица классов RealWaste пуста"
    for class_name, (category_id, object_name) in CLASS_TO_CATEGORY.items():
        assert category_id in CATEGORY_IDS, f"{class_name} → неизвестная категория {category_id}"
        assert object_name, f"{class_name} без названия предмета"


def test_coco_classes_map_to_existing_categories() -> None:
    assert COCO_ID_TO_CATEGORY, "таблица классов COCO пуста"
    for coco_id, (category_id, object_name) in COCO_ID_TO_CATEGORY.items():
        assert category_id in CATEGORY_IDS, f"COCO {coco_id} → неизвестная категория {category_id}"
        assert object_name, f"COCO {coco_id} без названия предмета"


def test_realwaste_covers_main_recyclables() -> None:
    """Пять основных баков должны быть достижимы через классификатор."""
    reachable = {category_id for category_id, _ in CLASS_TO_CATEGORY.values()}
    assert {"plastic", "glass", "paper", "metal", "organic"} <= reachable


def test_training_table_matches_dataset_classes() -> None:
    """Таблица обучения описывает ровно те девять классов, что есть в RealWaste."""
    from prediction.train_classifier import REALWASTE_CLASSES_RU

    expected = {
        "Cardboard",
        "Food Organics",
        "Glass",
        "Metal",
        "Miscellaneous Trash",
        "Paper",
        "Plastic",
        "Textile Trash",
        "Vegetation",
    }
    assert set(REALWASTE_CLASSES_RU) == expected
