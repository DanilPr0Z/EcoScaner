"""Распознавание отходов — реализация протокола `Classifier`.

Материал определяет классификатор, обученный на RealWaste
(`prediction/train_classifier.py`): пользователь снимает один предмет крупно,
и вопрос стоит «из чего это», а не «где это на кадре». Такой классификатор
знает картон, текстиль и смешанный мусор — то, чего в COCO попросту нет.

Детектор COCO при этом остаётся, но только ради рамки: он подсказывает, где
на снимке предмет, и иногда даёт название точнее («пластиковая бутылка» вместо
«пластик»). На решение о категории он не влияет и отключается настройкой.

Обе модели грузятся один раз при старте, инференс уходит в отдельный поток —
иначе на время счёта встаёт весь сервер. Фото остаётся в памяти, на диск
ничего не пишется.

Включается через CLASSIFIER=ml. Зависимости — requirements-ml.txt.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.recognition.base import Box, Prediction, TechRow
from prediction.model_training import COCO_CLASSES_RU
from prediction.train_classifier import WASTE_CLASSES_RU

#: Названия категорий в моделях русские, в справочнике — id латиницей.
_CATEGORY_ID_BY_RU: dict[str, str] = {
    "пластик": "plastic",
    "стекло": "glass",
    "бумага": "paper",
    "металл": "metal",
    "органика": "organic",
    "особые отходы": "special",
    "прочее": "other",
}


def _translate(table: dict[Any, tuple[str, str]], where: str) -> dict[Any, tuple[str, str]]:
    """Переводит таблицу «ключ → (русская категория, предмет)» в id справочника."""
    unknown = {category for category, _ in table.values()} - set(_CATEGORY_ID_BY_RU)
    if unknown:
        raise RuntimeError(
            f"В {where} есть категории, которых нет в справочнике: {sorted(unknown)}. "
            "Добавьте их в _CATEGORY_ID_BY_RU."
        )
    return {
        key: (_CATEGORY_ID_BY_RU[category], name) for key, (category, name) in table.items()
    }


#: Класс RealWaste → (id категории, название предмета).
CLASS_TO_CATEGORY = _translate(WASTE_CLASSES_RU, "prediction/train_classifier.py")
#: COCO-класс → (id категории, название предмета). Нужен только для уточнения названия.
COCO_ID_TO_CATEGORY = _translate(COCO_CLASSES_RU, "prediction/model_training.py")


class MLClassifier:
    """Классификатор материала + детектор для рамки."""

    name = "ml"

    def __init__(self) -> None:
        self._classifier: Any | None = None
        self._detector: Any | None = None

    # --- загрузка моделей -------------------------------------------------

    def _load_classifier(self) -> Any:
        if self._classifier is None:
            from ultralytics import YOLO

            weights = Path(settings.waste_classifier_weights)
            if not weights.is_absolute():
                weights = Path(__file__).resolve().parents[3] / weights
            if not weights.exists():
                raise RuntimeError(
                    f"Не найдены веса классификатора: {weights}\n"
                    "Обучите модель: python -m prediction.train_classifier"
                )
            self._classifier = YOLO(str(weights))
        return self._classifier

    def _load_detector(self) -> Any | None:
        if not settings.detector_weights:
            return None
        if self._detector is None:
            from ultralytics import YOLO

            self._detector = YOLO(settings.detector_weights)
        return self._detector

    def warmup(self) -> None:
        """Грузит веса заранее — иначе первый пользователь ждёт лишние секунды."""
        self._load_classifier()
        self._load_detector()

    # --- инференс ---------------------------------------------------------

    def _detect_box(self, picture: Any) -> tuple[Box, str, float] | None:
        """Рамка вокруг предмета. Возвращает (рамка, id категории, уверенность)."""
        detector = self._load_detector()
        if detector is None:
            return None

        results = detector.predict(
            picture, conf=settings.detector_confidence, verbose=False
        )
        if not results:
            return None
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return None

        coordinates = boxes.xyxy.cpu().numpy()
        class_ids = boxes.cls.cpu().numpy().astype(int)
        confidences = boxes.conf.cpu().numpy()

        best = max(range(len(class_ids)), key=lambda i: float(confidences[i]))
        class_id = int(class_ids[best])
        if class_id not in COCO_ID_TO_CATEGORY:
            return None

        category_id, object_name = COCO_ID_TO_CATEGORY[class_id]
        confidence = float(confidences[best])
        width, height = picture.size
        left, top, right, bottom = (float(v) for v in coordinates[best])

        # Ширина и высота ограничены снизу: схема Box требует строго положительных
        # значений, а вырожденная рамка от детектора уронила бы запрос в 500.
        box = Box(
            left=min(99.0, max(0.0, left / width * 100)),
            top=min(99.0, max(0.0, top / height * 100)),
            width=min(100.0, max(0.5, (right - left) / width * 100)),
            height=min(100.0, max(0.5, (bottom - top) / height * 100)),
            label=f"{object_name} · {confidence:.2f}",
        )
        return box, category_id, confidence

    def _run(self, image: bytes) -> Prediction | None:
        from PIL import Image, UnidentifiedImageError

        try:
            picture = Image.open(io.BytesIO(image)).convert("RGB")
        except (UnidentifiedImageError, OSError):
            return None

        results = self._load_classifier().predict(picture, verbose=False)
        if not results or results[0].probs is None:
            return None

        probs = results[0].probs
        names = results[0].names
        class_name = names[int(probs.top1)]
        confidence = float(probs.top1conf)

        if class_name not in CLASS_TO_CATEGORY:  # pragma: no cover - защита от чужих весов
            return None
        category_id, object_name = CLASS_TO_CATEGORY[class_name]

        tech = [
            TechRow(
                label=f"классификатор: {names[int(index)]}",
                score=f"{float(score):.2f}",
            )
            for index, score in zip(probs.top5[:3], probs.top5conf[:3])
        ]

        # Рамка появляется, только когда детектор реально нашёл предмет.
        # Общей «области анализа» на весь кадр по ТЗ быть не должно.
        boxes: list[Box] = []
        detected = self._detect_box(picture)
        # Детектор берём в дело, только если он согласен с классификатором.
        # На снимках отходов он охотно выдаёт что-нибудь постороннее — на фото
        # картона может «увидеть» хот-дог, — и рисовать рамку вокруг того, чего
        # там нет, хуже, чем не рисовать её вовсе.
        if detected is not None and detected[1] == category_id:
            box, _, detected_confidence = detected
            boxes = [box]
            # Название от детектора конкретнее: «пластиковая бутылка» вместо «пластик».
            object_name = box.label.split(" · ")[0]
            tech.append(
                TechRow(label=f"детектор: {object_name}", score=f"{detected_confidence:.2f}")
            )

        return Prediction(
            category_id=category_id,
            object_name=object_name,
            confidence=min(0.99, confidence),
            boxes=boxes,
            tech=tech,
        )

    async def predict(self, image: bytes, content_type: str) -> Prediction | None:
        # Инференс блокирует поток, поэтому уводим его в пул.
        return await asyncio.to_thread(self._run, image)
