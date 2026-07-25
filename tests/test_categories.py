from __future__ import annotations

from httpx import AsyncClient

from app.data.seed_data import CATEGORIES


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "appName": "BinGo API", "classifier": "stub"}


async def test_list_categories(client: AsyncClient) -> None:
    response = await client.get("/categories")
    assert response.status_code == 200

    body = response.json()
    assert len(body) == len(CATEGORIES)
    assert [c["id"] for c in body] == [c["id"] for c in CATEGORIES]

    plastic = body[0]
    assert plastic["name"] == "Пластик"
    assert plastic["binLabel"] == "Жёлтый бак · пластик"
    assert len(plastic["prep"]) == 3
    assert len(plastic["items"]) == 8
    assert plastic["items"][0]["isAccepted"] is True
    assert plastic["items"][-1]["isAccepted"] is False


async def test_get_category(client: AsyncClient) -> None:
    response = await client.get("/categories/glass")
    assert response.status_code == 200
    assert response.json()["name"] == "Стекло"


async def test_get_category_not_found(client: AsyncClient) -> None:
    response = await client.get("/categories/wood")
    assert response.status_code == 404


async def test_search_response_shape(client: AsyncClient) -> None:
    """Поведение поиска разобрано в tests/test_search.py — здесь только форма ответа."""
    response = await client.get("/guide/search", params={"q": "бутылка"})
    assert response.status_code == 200

    body = response.json()
    assert set(body) == {"query", "total", "items", "categories"}
    assert body["total"] == len(body["items"]) > 0
    assert all(
        {"categoryId", "categoryName", "categoryColor", "matchedIn", "score"} <= set(item)
        for item in body["items"]
    )
