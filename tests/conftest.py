from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

# БД для тестов подменяем до импорта приложения — настройки читаются один раз при импорте.
_TEST_DB = Path(tempfile.gettempdir()) / "bingo_test.db"
_TEST_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"
os.environ["CLASSIFIER"] = "stub"

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.services.recognition.stub import StubClassifier  # noqa: E402


def _sample(recognized: bool) -> bytes:
    """Подбирает байты, на которых заглушка даёт (или не даёт) результат.

    Заглушка детерминирована хэшем, поэтому подобранные образцы стабильны.
    """
    classifier = StubClassifier()
    for i in range(1000):
        payload = f"bingo-test-sample-{i}".encode()
        prediction = asyncio.run(classifier.predict(payload, "image/jpeg"))
        if (prediction is not None) is recognized:
            return payload
    raise RuntimeError("Не удалось подобрать тестовый образец изображения")


#: Байты, которые заглушка уверенно распознаёт.
RECOGNIZED_IMAGE = _sample(recognized=True)
#: Байты, на которых заглушка отвечает «не распознано» (проверяем экран ошибки).
UNRECOGNIZED_IMAGE = _sample(recognized=False)


@pytest_asyncio.fixture(scope="session")
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test/api/v1") as ac:
            yield ac


@pytest.fixture
def device_id() -> str:
    """Свежий пользователь на каждый тест — истории между тестами не смешиваются."""
    return str(uuid.uuid4())


@pytest.fixture
def headers(device_id: str) -> dict[str, str]:
    return {"X-Device-Id": device_id}


def upload(image: bytes = RECOGNIZED_IMAGE, content_type: str = "image/jpeg") -> dict:
    return {"file": ("photo.jpg", image, content_type)}
