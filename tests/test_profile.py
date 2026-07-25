from __future__ import annotations

from datetime import date, timedelta

from httpx import AsyncClient

from app.services.gamification import build_badges, compute_streak
from tests.conftest import upload


async def test_empty_profile(client: AsyncClient, headers: dict[str, str]) -> None:
    response = await client.get("/profile", headers=headers)
    assert response.status_code == 200

    body = response.json()
    assert body["points"] == 0
    assert body["scanCount"] == 0
    assert body["streak"] == 0
    assert body["mix"] == []
    assert all(badge["achieved"] is False for badge in body["badges"])


async def test_profile_after_scans(client: AsyncClient, headers: dict[str, str]) -> None:
    await client.post("/scan", files=upload(), headers=headers)
    await client.post("/scan/manual", json={"categoryId": "paper"}, headers=headers)

    body = (await client.get("/profile", headers=headers)).json()
    assert body["scanCount"] == 2
    assert body["points"] == 50
    assert body["streak"] == 1
    assert body["categoriesUsed"] == 2
    assert body["totalCategories"] == 7
    assert sum(entry["count"] for entry in body["mix"]) == 2
    assert round(sum(entry["share"] for entry in body["mix"]), 3) == 1.0

    badges = {badge["id"]: badge["achieved"] for badge in body["badges"]}
    assert badges["first_scan"] is True
    assert badges["ten_scans"] is False


async def test_history_limit_and_order(client: AsyncClient, headers: dict[str, str]) -> None:
    for category_id in ("plastic", "glass", "paper"):
        await client.post("/scan/manual", json={"categoryId": category_id}, headers=headers)

    body = (await client.get("/profile/history", params={"limit": 2}, headers=headers)).json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    # Свежие сверху.
    assert body["items"][0]["categoryId"] == "paper"
    assert set(body["items"][0]) >= {"id", "categoryName", "categoryColor", "objectName", "createdAt"}


async def test_clear_history(client: AsyncClient, headers: dict[str, str]) -> None:
    scan = (await client.post("/scan", files=upload(), headers=headers)).json()
    await client.post(f"/scan/{scan['scanId']}/correct", json={"categoryId": "glass"}, headers=headers)

    response = await client.delete("/profile/history", headers=headers)
    assert response.status_code == 204

    profile = (await client.get("/profile", headers=headers)).json()
    assert profile["scanCount"] == 0
    assert profile["points"] == 0
    assert (await client.get("/profile/history", headers=headers)).json()["total"] == 0


async def test_profile_is_isolated_per_device(client: AsyncClient, headers: dict[str, str]) -> None:
    await client.post("/scan/manual", json={"categoryId": "metal"}, headers=headers)

    other = {"X-Device-Id": "99999999-8888-7777-6666-555555555555"}
    assert (await client.get("/profile", headers=other)).json()["scanCount"] == 0
    assert (await client.get("/profile", headers=headers)).json()["scanCount"] == 1


def test_compute_streak() -> None:
    today = date(2026, 7, 25)
    assert compute_streak(set(), today) == 0
    assert compute_streak({today}, today) == 1
    assert compute_streak({today, today - timedelta(days=1)}, today) == 2
    # Пропущенный день обрывает серию.
    assert compute_streak({today, today - timedelta(days=2)}, today) == 1
    # Вчерашняя серия без сегодняшнего скана уже не считается — как было в дизайне.
    assert compute_streak({today - timedelta(days=1)}, today) == 0


def test_badges() -> None:
    five = {"plastic", "glass", "paper", "metal", "organic"}
    badges = {b.id: b.achieved for b in build_badges(10, five | {"special"}, 7)}
    assert all(badges.values())

    badges = {b.id: b.achieved for b in build_badges(1, {"plastic"}, 1)}
    assert badges["first_scan"] is True
    assert badges["ten_scans"] is False
    assert badges["all_five_bins"] is False
    assert badges["week_streak"] is False
    assert badges["hazardous"] is False
