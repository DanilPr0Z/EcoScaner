from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.text_search import score_token, tokenize


async def search(client: AsyncClient, query: str, **params) -> dict:
    response = await client.get("/guide/search", params={"q": query, **params})
    assert response.status_code == 200
    return response.json()


async def test_finds_regardless_of_case(client: AsyncClient) -> None:
    """SQLite LIKE не умеет регистр кириллицы — проверяем, что мы умеем."""
    body = await search(client, "бутылка")
    names = [item["name"] for item in body["items"]]
    assert "Бутылка из-под воды" in names
    assert "Стеклянная бутылка" in names


@pytest.mark.parametrize("query", ["бутылка", "бутылки", "бутылке", "бутылку", "бутыл"])
async def test_finds_word_forms(client: AsyncClient, query: str) -> None:
    body = await search(client, query)
    assert "Бутылка из-под воды" in [item["name"] for item in body["items"]]


async def test_head_word_outranks_modifier(client: AsyncClient) -> None:
    """По «бутылки» сама бутылка должна быть выше «Крышки от бутылки».

    Первое слово короткого названия — это сам предмет, остальные его уточняют.
    """
    body = await search(client, "бутылки")
    names = [item["name"] for item in body["items"]]
    assert names.index("Бутылка из-под воды") < names.index("Крышка от бутылки")


async def test_tolerates_one_typo(client: AsyncClient) -> None:
    body = await search(client, "бутулка")
    assert "Бутылка из-под воды" in [item["name"] for item in body["items"]]


async def test_yo_is_equal_to_ye(client: AsyncClient) -> None:
    """«Жёлтый бак» должен находиться и по «желтый»."""
    by_yo = await search(client, "жёлтый")
    by_ye = await search(client, "желтый")
    assert [c["id"] for c in by_yo["categories"]] == [c["id"] for c in by_ye["categories"]] == ["plastic"]


async def test_searches_inside_category_description(client: AsyncClient) -> None:
    """«метан» встречается только в подсказке про органику — по нему находим саму категорию."""
    body = await search(client, "метан")
    assert [c["id"] for c in body["categories"]] == ["organic"]
    assert body["categories"][0]["matchedIn"] == ["hint"]


async def test_searches_inside_prep_steps(client: AsyncClient) -> None:
    """«компостируется» есть только в шагах подготовки органики."""
    body = await search(client, "компостируется")
    assert "organic" in [c["id"] for c in body["categories"]]
    assert "prep" in next(c for c in body["categories"] if c["id"] == "organic")["matchedIn"]


async def test_searches_inside_becomes(client: AsyncClient) -> None:
    """«биогаз» встречается только в поле «станет» у органики."""
    body = await search(client, "биогаз")
    organic = next(c for c in body["categories"] if c["id"] == "organic")
    assert organic["matchedIn"] == ["becomes"]


async def test_compound_word_finds_its_base(client: AsyncClient) -> None:
    """«стекловата» начинается со «стекло» — этого достаточно, чтобы найти категорию."""
    body = await search(client, "стекловата")
    assert "glass" in [c["id"] for c in body["categories"]]


async def test_name_ranks_above_note(client: AsyncClient) -> None:
    """Совпадение в названии предмета важнее совпадения в примечании."""
    body = await search(client, "крышка")
    by_name = [item for item in body["items"] if item["matchedIn"] == ["name"]]
    by_note = [item for item in body["items"] if item["matchedIn"] == ["note"]]
    assert by_name and by_note

    assert body["items"][0]["matchedIn"] == ["name"]
    assert min(item["score"] for item in by_name) > max(item["score"] for item in by_note)


async def test_matched_in_reports_the_field(client: AsyncClient) -> None:
    body = await search(client, "PET")
    hit = next(item for item in body["items"] if item["name"] == "Бутылка из-под воды")
    assert hit["matchedIn"] == ["note"]


async def test_category_name_pulls_its_items(client: AsyncClient) -> None:
    """Запрос «стекло» показывает и категорию, и её предметы."""
    body = await search(client, "стекло")
    assert "glass" in [c["id"] for c in body["categories"]]
    assert {item["categoryId"] for item in body["items"]} >= {"glass"}


async def test_multiple_words_require_all(client: AsyncClient) -> None:
    """Слова запроса объединяются по И, а не по ИЛИ."""
    both = await search(client, "консервная банка")
    assert "Консервная банка" in [item["name"] for item in both["items"]]

    nothing = await search(client, "консервная гитара")
    assert nothing["total"] == 0


async def test_limit_truncates_but_total_is_full(client: AsyncClient) -> None:
    full = await search(client, "банка")
    assert full["total"] >= 3

    limited = await search(client, "банка", limit=1)
    assert limited["total"] == full["total"]
    assert len(limited["items"]) == 1
    # Обрезается хвост, а не голова: первым остаётся самый релевантный.
    assert limited["items"][0]["name"] == full["items"][0]["name"]


async def test_empty_result(client: AsyncClient) -> None:
    body = await search(client, "цезий")
    assert body == {"query": "цезий", "total": 0, "items": [], "categories": []}


async def test_punctuation_only_query(client: AsyncClient) -> None:
    body = await search(client, "!!!")
    assert body["total"] == 0
    assert body["categories"] == []


def test_tokenize() -> None:
    assert tokenize("Бутылка из-под воды") == ("бутылка", "из", "под", "воды")
    assert tokenize("Жёлтый бак · пластик") == ("желтый", "бак", "пластик")
    assert tokenize("  ") == ()


def test_score_token_ranking() -> None:
    assert score_token("бутылка", "бутылка") == 1.0
    # Точное совпадение > недописанное слово > другая словоформа > опечатка.
    assert (
        score_token("бутылка", "бутылка")
        > score_token("бутыл", "бутылка")
        > score_token("бутылки", "бутылка")
        > score_token("бутулка", "бутылка")
        > 0
    )
    # Короткие обрывки не должны цеплять всё подряд.
    assert score_token("ка", "бутылка") == 0.0
    assert score_token("банан", "бутылка") == 0.0
