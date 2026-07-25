"""Заглушка распознавания — работает, пока нет реальной ML-модели.

Результат детерминирован хэшем картинки: одно и то же фото всегда даёт
один и тот же ответ. Это удобно и для демо, и для тестов.
"""

from __future__ import annotations

import hashlib
import random

from app.data.seed_data import COCO_CLASSES, IMAGENET_KEYS
from app.services.recognition.base import Box, Prediction, TechRow

#: Доля изображений, на которых заглушка «не узнаёт» предмет — чтобы фронтовый
#: экран ошибки и ручной выбор категории тоже можно было проверить.
UNRECOGNIZED_RATE = 0.05

_DETECTOR_POOL: list[tuple[str, str, str]] = [
    (coco_label, category_id, object_name)
    for coco_label, (category_id, object_name) in COCO_CLASSES.items()
]

_IMAGENET_BY_CATEGORY: dict[str, list[str]] = {}
for _key, _category_id, _ru in IMAGENET_KEYS:
    _IMAGENET_BY_CATEGORY.setdefault(_category_id, []).append(_key)


class StubClassifier:
    """Реализация протокола `Classifier` без ML."""

    name = "stub"

    async def predict(self, image: bytes, content_type: str) -> Prediction | None:
        digest = hashlib.sha256(image).digest()
        rnd = random.Random(int.from_bytes(digest[:8], "big"))

        if rnd.random() < UNRECOGNIZED_RATE:
            return None

        coco_label, category_id, object_name = rnd.choice(_DETECTOR_POOL)
        confidence = round(rnd.uniform(0.55, 0.95), 2)
        detector_score = round(rnd.uniform(0.45, min(0.98, confidence + 0.05)), 2)

        left = round(rnd.uniform(6, 28), 1)
        top = round(rnd.uniform(6, 24), 1)
        box = Box(
            left=left,
            top=top,
            width=round(min(rnd.uniform(42, 62), 100 - left), 1),
            height=round(min(rnd.uniform(46, 66), 100 - top), 1),
            label=f"{object_name} · {detector_score:.2f}",
        )

        imagenet_pool = _IMAGENET_BY_CATEGORY.get(category_id, [coco_label])
        tech = [
            TechRow(label=f"детектор: {coco_label}", score=f"{detector_score:.2f}"),
            TechRow(
                label=f"классификатор: {rnd.choice(imagenet_pool)}",
                score=f"{round(confidence, 2):.2f}",
            ),
            TechRow(
                label=f"классификатор: {rnd.choice(imagenet_pool)}",
                score=f"{round(rnd.uniform(0.05, 0.4), 2):.2f}",
            ),
        ]

        return Prediction(
            category_id=category_id,
            object_name=object_name,
            confidence=confidence,
            boxes=[box],
            tech=tech,
        )
