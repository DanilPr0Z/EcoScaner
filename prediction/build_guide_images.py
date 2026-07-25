"""Готовит обзорную картинку для каждой категории справочника.

Снимки берутся из Openverse — там они под свободными лицензиями, и показывать
их в интерфейсе можно без оговорок. Из обучающих датасетов картинки не берём:
у RealWaste лицензия CC BY-NC-SA, да и кадры с конвейера полигона выглядят
случайно — под «Стеклом» мог оказаться ящик пивных бутылок.

Отдельные картинки для каждого предмета готовит build_item_images.

    python -m prediction.build_guide_images
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "app" / "static" / "guide"

#: Категория справочника → поисковый запрос. Запросы описывают вторсырьё,
#: а не напиток: «glass bottle» вернул бы пиво, что рядом со «Стеклом» неуместно.
CATEGORY_QUERIES: dict[str, str] = {
    "plastic": "plastic bottles recycling",
    "glass": "glass jars recycling",
    "paper": "cardboard boxes recycling",
    "metal": "aluminium cans recycling",
    "organic": "food waste compost",
    "special": "electronic waste batteries",
    "other": "mixed household waste",
}


def main() -> None:
    from prediction.build_item_images import ATTRIBUTION, download, search, _ssl_context

    context = _ssl_context()
    TARGET.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = {}
    if ATTRIBUTION.exists():
        import json as _json

        credits = _json.loads(ATTRIBUTION.read_text(encoding="utf-8"))

    for category, query in CATEGORY_QUERIES.items():
        destination = TARGET / f"{category}.jpg"
        destination.unlink(missing_ok=True)

        saved = False
        for candidate in search(query, context):
            url = candidate.get("url")
            if url and download(url, destination, context):
                credits[category] = {
                    "item": f"категория {category}",
                    "title": candidate.get("title"),
                    "creator": candidate.get("creator"),
                    "license": candidate.get("license"),
                    "source": candidate.get("foreign_landing_url"),
                }
                saved = True
                break
        print(f"  {'✓' if saved else '×'} {category:10} {query}")

    import json as _json

    ATTRIBUTION.write_text(
        _json.dumps(credits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nГотово: {TARGET.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
