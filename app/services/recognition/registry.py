"""Выбор реализации классификатора по настройке `CLASSIFIER`.

Единственное место, где приложение узнаёт, какая модель используется.
Когда появится реальная модель — кладём её в `app/services/recognition/ml.py`
с методом `predict()` из протокола `Classifier` и ставим `CLASSIFIER=ml` в .env.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.services.recognition.base import Classifier
from app.services.recognition.stub import StubClassifier


@lru_cache
def get_classifier() -> Classifier:
    name = settings.classifier.strip().lower()

    if name == "stub":
        return StubClassifier()

    if name == "ml":
        try:
            from app.services.recognition.ml import MLClassifier
        except ImportError as exc:  # pragma: no cover - сработает, когда модели ещё нет
            raise RuntimeError(
                "CLASSIFIER=ml, но модуль app/services/recognition/ml.py отсутствует "
                "или не импортируется. Добавьте реализацию MLClassifier или верните "
                "CLASSIFIER=stub."
            ) from exc
        return MLClassifier()

    raise RuntimeError(f"Неизвестное значение CLASSIFIER={settings.classifier!r}. Допустимо: stub, ml.")
