"""Распознавание через YOLOv8 — реализация протокола `Classifier`.

Адаптер над моделью из `prediction/model_training.py`. Сама функция
`predict_yolo` здесь не вызывается: она принимает путь к файлу, грузит модель
на каждый вызов и пишет result.jpg на диск — для сервера не подходит. Мы
переиспользуем её таблицу классов, а инференс делаем по-своему:

  * фото приходит байтами и остаётся в памяти — на диск ничего не пишем;
  * модель загружается один раз и живёт до перезапуска;
  * инференс уходит в поток, чтобы не блокировать событийный цикл;
  * рамки пересчитываются в проценты, потому что фронт рисует их поверх
    своего локального превью.

Включается через CLASSIFIER=ml в .env. Зависимости — requirements-ml.txt.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from app.core.config import settings
from app.services.recognition.base import Box, Prediction, TechRow
from prediction.model_training import COCO_CLASSES_RU

#: Названия категорий у модели — русские, у нас id латиницей.
_CATEGORY_ID_BY_RU: dict[str, str] = {
    "пластик": "plastic",
    "стекло": "glass",
    "бумага": "paper",
    "металл": "metal",
    "органика": "organic",
    "особые отходы": "special",
    "прочее": "other",
}

#: COCO-класс → (наш id категории, русское название предмета).
#: Собирается из таблицы модели, чтобы не заводить вторую копию.
COCO_ID_TO_CATEGORY: dict[int, tuple[str, str]] = {
    coco_id: (_CATEGORY_ID_BY_RU[category_ru], object_name)
    for coco_id, (category_ru, object_name) in COCO_CLASSES_RU.items()
    if category_ru in _CATEGORY_ID_BY_RU
}

_UNKNOWN_CATEGORIES = {
    category_ru
    for category_ru, _ in COCO_CLASSES_RU.values()
    if category_ru not in _CATEGORY_ID_BY_RU
}
if _UNKNOWN_CATEGORIES:  # pragma: no cover - страховка на случай правок таблицы
    raise RuntimeError(
        "В prediction/model_training.py появились категории, которых нет в справочнике: "
        f"{sorted(_UNKNOWN_CATEGORIES)}. Добавьте их в _CATEGORY_ID_BY_RU."
    )


class MLClassifier:
    """Реализация протокола `Classifier` поверх YOLOv8."""

    name = "ml"

    def __init__(self) -> None:
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(settings.yolo_weights)
        return self._model

    def warmup(self) -> None:
        """Загружает веса заранее — иначе первый пользователь ждёт лишние секунды."""
        self._load_model()

    def _run(self, image: bytes) -> Prediction | None:
        """Синхронный инференс. Вызывается в отдельном потоке."""
        from PIL import Image, UnidentifiedImageError

        try:
            picture = Image.open(io.BytesIO(image)).convert("RGB")
        except (UnidentifiedImageError, OSError):
            return None

        width, height = picture.size
        results = self._load_model().predict(
            picture, conf=settings.yolo_confidence, verbose=False
        )
        if not results:
            return None

        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None

        coordinates = boxes.xyxy.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)
        confidences = boxes.conf.cpu().numpy()

        # Все распознанные объекты, от уверенных к сомнительным.
        detections = sorted(
            (
                (float(confidences[i]), int(class_ids[i]), coordinates[i])
                for i in range(len(class_ids))
                if int(class_ids[i]) in COCO_ID_TO_CATEGORY
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if not detections:
            return None

        confidence, class_id, xyxy = detections[0]
        category_id, object_name = COCO_ID_TO_CATEGORY[class_id]

        left, top, right, bottom = (float(value) for value in xyxy)
        box = Box(
            left=max(0.0, left / width * 100),
            top=max(0.0, top / height * 100),
            width=min(100.0, (right - left) / width * 100),
            height=min(100.0, (bottom - top) / height * 100),
            label=f"{object_name} · {confidence:.2f}",
        )

        tech = [
            TechRow(
                label=f"детектор: {COCO_ID_TO_CATEGORY[detected_class][1]}",
                score=f"{detected_confidence:.2f}",
            )
            for detected_confidence, detected_class, _ in detections[:3]
        ]

        return Prediction(
            category_id=category_id,
            object_name=object_name,
            confidence=min(0.99, confidence),
            boxes=[box],
            tech=tech,
        )

    async def predict(self, image: bytes, content_type: str) -> Prediction | None:
        # YOLO считает на CPU и блокирует поток, поэтому уводим в пул —
        # иначе на время инференса встаёт весь сервер.
        return await asyncio.to_thread(self._run, image)
