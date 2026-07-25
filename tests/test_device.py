from __future__ import annotations

import asyncio
import uuid

from httpx import AsyncClient


async def test_parallel_first_requests_create_one_device(client: AsyncClient) -> None:
    """Первый визит: несколько запросов приходят одновременно.

    Так ведёт себя экран профиля — он грузит /profile и /profile/history разом.
    Раньше оба запроса не находили устройство, оба пытались его создать,
    и один падал с UNIQUE constraint failed: devices.id.
    """
    headers = {"X-Device-Id": str(uuid.uuid4())}

    responses = await asyncio.gather(
        client.get("/profile", headers=headers),
        client.get("/profile/history", headers=headers),
        client.get("/profile", headers=headers),
        client.get("/profile/history", headers=headers),
    )

    assert [r.status_code for r in responses] == [200, 200, 200, 200]
    assert responses[0].json()["deviceId"] == headers["X-Device-Id"]


async def test_parallel_first_scans(client: AsyncClient) -> None:
    """Та же гонка, но на записывающем эндпоинте."""
    headers = {"X-Device-Id": str(uuid.uuid4())}

    responses = await asyncio.gather(
        client.post("/scan/manual", json={"categoryId": "glass"}, headers=headers),
        client.post("/scan/manual", json={"categoryId": "paper"}, headers=headers),
    )

    assert [r.status_code for r in responses] == [201, 201]
    assert (await client.get("/profile", headers=headers)).json()["scanCount"] == 2


async def test_device_is_reused_between_requests(client: AsyncClient) -> None:
    headers = {"X-Device-Id": str(uuid.uuid4())}

    await client.post("/scan/manual", json={"categoryId": "metal"}, headers=headers)
    profile = (await client.get("/profile", headers=headers)).json()

    assert profile["scanCount"] == 1
    assert profile["points"] == 25
