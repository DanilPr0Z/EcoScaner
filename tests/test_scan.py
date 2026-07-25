from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import RECOGNIZED_IMAGE, UNRECOGNIZED_IMAGE, upload


async def test_scan_returns_result_with_category_content(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post("/scan", files=upload(), headers=headers)
    assert response.status_code == 201

    body = response.json()
    assert body["scanId"]
    assert body["isManual"] is False
    assert 0 < body["confidence"] <= 1
    # Карточка результата заполняется из одного ответа — контент категории вложен.
    assert set(body["category"]) >= {"id", "name", "color", "binLabel", "hint", "prep", "decay", "becomes", "avoid"}
    assert body["boxes"] and body["tech"]
    # Первое сканирование: 10 за скан + 15 за новую категорию.
    assert body["pointsAwarded"] == 25
    assert body["totalPoints"] == 25


async def test_scan_is_deterministic(client: AsyncClient, headers: dict[str, str]) -> None:
    first = await client.post("/scan", files=upload(), headers=headers)
    second = await client.post("/scan", files=upload(), headers=headers)

    assert first.json()["category"]["id"] == second.json()["category"]["id"]
    # Второй скан той же категории — только 10 очков, бонуса за новую категорию нет.
    assert second.json()["pointsAwarded"] == 10
    assert second.json()["totalPoints"] == 35


async def test_scan_unrecognized(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post("/scan", files=upload(UNRECOGNIZED_IMAGE), headers=headers)
    assert response.status_code == 422
    assert "не похож" in response.json()["detail"]


async def test_scan_rejects_non_image(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post(
        "/scan", files={"file": ("note.txt", b"hello", "text/plain")}, headers=headers
    )
    assert response.status_code == 415


async def test_scan_rejects_empty_file(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post("/scan", files=upload(b""), headers=headers)
    assert response.status_code == 400


async def test_scan_requires_device_header(client: AsyncClient) -> None:
    response = await client.post("/scan", files=upload())
    assert response.status_code == 400
    assert "X-Device-Id" in response.json()["detail"]


async def test_scan_rejects_malformed_device_header(client: AsyncClient) -> None:
    response = await client.post("/scan", files=upload(), headers={"X-Device-Id": "no spaces!"})
    assert response.status_code == 400


async def test_manual_scan(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post("/scan/manual", json={"categoryId": "metal"}, headers=headers)
    assert response.status_code == 201

    body = response.json()
    assert body["isManual"] is True
    assert body["confidence"] == 1.0
    assert body["category"]["id"] == "metal"
    assert body["objectName"] == "указано вручную"


async def test_manual_scan_unknown_category(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.post("/scan/manual", json={"categoryId": "wood"}, headers=headers)
    assert response.status_code == 404


async def test_correct_scan_moves_it_to_another_category(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    scan = (await client.post("/scan", files=upload(), headers=headers)).json()
    predicted = scan["category"]["id"]
    corrected = "glass" if predicted != "glass" else "paper"

    response = await client.post(
        f"/scan/{scan['scanId']}/correct", json={"categoryId": corrected}, headers=headers
    )
    assert response.status_code == 200

    body = response.json()
    assert body["category"]["id"] == corrected
    assert body["isManual"] is True
    # Исправление уточняет уже начисленный скан, а не добавляет новый.
    assert body["totalPoints"] == 25

    history = (await client.get("/profile/history", headers=headers)).json()
    assert history["total"] == 1
    assert history["items"][0]["categoryId"] == corrected


async def test_correct_scan_of_another_device(client: AsyncClient, headers: dict[str, str]) -> None:
    scan = (await client.post("/scan", files=upload(), headers=headers)).json()
    other = {"X-Device-Id": "11111111-2222-3333-4444-555555555555"}

    response = await client.post(
        f"/scan/{scan['scanId']}/correct", json={"categoryId": "glass"}, headers=other
    )
    assert response.status_code == 404


async def test_scan_reads_full_image(client: AsyncClient, headers: dict[str, str]) -> None:
    """Файл читается целиком, а не первым чанком: большой файл проходит и распознаётся."""
    big = RECOGNIZED_IMAGE + b"\x00" * (200 * 1024)
    response = await client.post("/scan", files=upload(big), headers=headers)
    assert response.status_code in (201, 422)
