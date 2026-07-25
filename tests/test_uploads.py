"""Сохранение снимков и память об исправлениях."""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from app.services import uploads
from tests.conftest import RECOGNIZED_IMAGE, upload


def test_hash_is_stable() -> None:
    assert uploads.image_hash(b"a") == uploads.image_hash(b"a")
    assert uploads.image_hash(b"a") != uploads.image_hash(b"b")


async def test_scan_remembers_correction(client: AsyncClient) -> None:
    """Исправленный кадр при повторной загрузке сразу определяется верно.

    Пользователь не должен править один и тот же снимок после каждой
    перезагрузки страницы — ради этого исправления и запоминаются.
    """
    headers = {"X-Device-Id": str(uuid.uuid4())}

    first = (await client.post("/scan", files=upload(), headers=headers)).json()
    predicted = first["category"]["id"]
    corrected = "glass" if predicted != "glass" else "paper"

    await client.post(
        f"/scan/{first['scanId']}/correct",
        json={"categoryId": corrected},
        headers=headers,
    )

    again = (await client.post("/scan", files=upload(), headers=headers)).json()
    assert again["category"]["id"] == corrected
    assert again["isManual"] is True
    assert again["objectName"] == "по вашему исправлению"


async def test_correction_applies_to_other_devices(client: AsyncClient) -> None:
    """Исправление одного человека помогает следующему: кадр уже размечен."""
    author = {"X-Device-Id": str(uuid.uuid4())}
    other = {"X-Device-Id": str(uuid.uuid4())}

    scan = (await client.post("/scan", files=upload(), headers=author)).json()
    target = "metal" if scan["category"]["id"] != "metal" else "paper"
    await client.post(
        f"/scan/{scan['scanId']}/correct", json={"categoryId": target}, headers=author
    )

    assert (
        (await client.post("/scan", files=upload(), headers=other)).json()["category"]["id"]
        == target
    )


async def test_uncorrected_scan_is_not_forced(client: AsyncClient) -> None:
    """Без исправления ответ по-прежнему даёт модель, а не память."""
    headers = {"X-Device-Id": str(uuid.uuid4())}
    other_image = RECOGNIZED_IMAGE + b"\x00"

    body = (await client.post("/scan", files=upload(other_image), headers=headers)).json()
    assert body["isManual"] is False
    assert body["objectName"] != "по вашему исправлению"
