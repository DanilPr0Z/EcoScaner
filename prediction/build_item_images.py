"""Подбирает картинку для каждого предмета справочника.

Картинок по категориям мало: под «Пластиком» восемь разных предметов, и одна
общая фотография бутылки ничего не говорит про канистру или плёнку. Здесь
каждому предмету подбирается своя.

Берём Openverse — агрегатор снимков под свободными лицензиями. В отличие от
датасетов, которыми учим модель, эти картинки можно показывать в интерфейсе
без оговорок: рядом сохраняется автор и лицензия (см. attribution.json).

    python -m prediction.build_item_images
    python -m prediction.build_item_images --only plastic

Запрос строится по английскому названию: русские названия Openverse почти
не понимает. Соответствия — в ITEM_QUERIES.
"""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "app" / "static" / "guide" / "items"
ATTRIBUTION = PROJECT_ROOT / "app" / "static" / "guide" / "attribution.json"

API = "https://api.openverse.org/v1/images/"
SIZE = 640

#: Название предмета в справочнике → поисковый запрос на английском.
#: Запросы намеренно узкие: «bottle» вернёт что угодно, «plastic water bottle» —
#: то, что нужно показать рядом с этим пунктом.
ITEM_QUERIES: dict[str, str] = {
    # Пластик
    "Бутылка из-под воды": "plastic water bottle",
    "Флакон шампуня": "shampoo bottle",
    "Канистра, ведро": "plastic bucket",
    "Пакет-майка, плёнка": "plastic bag",
    "Крышка от бутылки": "bottle cap plastic",
    "Одноразовая посуда": "disposable plastic cup plate",
    "Тетрапак": "tetra pak carton",
    "Зубная щётка": "toothbrush",
    # Стекло
    "Стеклянная бутылка": "glass bottle",
    "Банка от консервов": "glass jar",
    "Стакан, бокал": "drinking glass",
    "Флакон духов": "perfume bottle",
    "Лампочка": "light bulb",
    "Зеркало": "mirror",
    "Керамическая кружка": "ceramic mug",
    "Оконное стекло": "window glass pane",
    # Бумага
    "Газета, журнал": "newspaper stack",
    "Картонная коробка": "cardboard box",
    "Книга": "book",
    "Офисная бумага": "office paper sheets",
    "Конверт, тетрадь": "envelope notebook",
    "Кассовый чек": "receipt paper",
    "Коробка от пиццы": "pizza box",
    "Салфетка": "paper napkin",
    # Металл
    "Банка из-под напитка": "aluminium drink can",
    "Консервная банка": "tin can food",
    "Металлическая крышка": "metal jar lid",
    "Чистая фольга": "aluminium foil",
    "Столовые приборы": "cutlery fork spoon",
    "Аэрозольный баллончик": "aerosol spray can",
    "Батарейка": "battery aa",
    "Тефлоновая кастрюля": "frying pan",
    # Органика
    "Кожура фруктов и овощей": "vegetable peelings",
    "Яблоко, банан, апельсин": "apple banana orange fruit",
    "Хлеб, крупы": "bread loaf",
    "Кофейная гуща, заварка": "coffee grounds",
    "Скорлупа яиц": "egg shells",
    "Кости": "animal bones food",
    "Чайный пакетик": "tea bag",
    "Растительное масло": "cooking oil bottle",
    # Особые отходы
    "Батарейка, аккумулятор": "batteries recycling",
    "Телефон, ноутбук": "old smartphone laptop",
    "Энергосберегающая лампа": "fluorescent lamp",
    "Градусник": "mercury thermometer",
    "Краска, растворитель": "paint can",
    "Лекарства": "pills medicine",
    # Прочее
    "Обувь, одежда": "old shoes clothes",
    "Мягкая игрушка": "teddy bear toy",
    "Подгузники, гигиена": "diapers",
    "Зубная щётка, ручка": "toothbrush pen",
}


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def search(query: str, context: ssl.SSLContext) -> list[dict]:
    params = urllib.parse.urlencode(
        {"q": query, "license_type": "commercial", "page_size": 8, "mature": "false"}
    )
    request = urllib.request.Request(
        f"{API}?{params}", headers={"User-Agent": "BinGo/1.0 (guide images)"}
    )
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        return json.load(response).get("results", [])


def download(url: str, destination: Path, context: ssl.SSLContext) -> bool:
    """Скачивает и приводит к квадрату. False, если картинка не пригодилась."""
    from PIL import Image

    request = urllib.request.Request(url, headers={"User-Agent": "BinGo/1.0"})
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            raw = response.read()
    except Exception:  # noqa: BLE001
        return False

    try:
        import io

        with Image.open(io.BytesIO(raw)) as image:
            image = image.convert("RGB")
            # Совсем мелкие снимки в интерфейсе выглядят мылом.
            if min(image.size) < 200:
                return False
            side = min(image.size)
            left = (image.width - side) // 2
            top = (image.height - side) // 2
            image = image.crop((left, top, left + side, top + side))
            image.resize((SIZE, SIZE), Image.Resampling.LANCZOS).save(
                destination, "JPEG", quality=82, optimize=True
            )
    except Exception:  # noqa: BLE001
        destination.unlink(missing_ok=True)
        return False
    return True


def slug(category_id: str, index: int) -> str:
    return f"{category_id}-{index}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Картинки для предметов справочника")
    parser.add_argument("--only", help="только эта категория")
    args = parser.parse_args()

    from app.data.seed_data import CATEGORIES

    context = _ssl_context()
    TARGET.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = {}
    if ATTRIBUTION.exists():
        credits = json.loads(ATTRIBUTION.read_text(encoding="utf-8"))

    missing: list[str] = []
    for category in CATEGORIES:
        if args.only and category["id"] != args.only:
            continue
        for index, item in enumerate(category["items"]):
            name = slug(category["id"], index)
            destination = TARGET / f"{name}.jpg"
            if destination.exists():
                continue

            query = ITEM_QUERIES.get(item["name"])
            if not query:
                missing.append(item["name"])
                continue

            saved = False
            for candidate in search(query, context):
                url = candidate.get("url")
                if url and download(url, destination, context):
                    credits[name] = {
                        "item": item["name"],
                        "title": candidate.get("title"),
                        "creator": candidate.get("creator"),
                        "license": candidate.get("license"),
                        "source": candidate.get("foreign_landing_url"),
                    }
                    saved = True
                    break

            print(f"  {'✓' if saved else '×'} {category['id']:8} {item['name'][:32]:34} {query}")
            if not saved:
                missing.append(item["name"])

    ATTRIBUTION.write_text(
        json.dumps(credits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    found = len(list(TARGET.glob("*.jpg")))
    print(f"\nКартинок: {found}. Авторы и лицензии — {ATTRIBUTION.name}")
    if missing:
        print(f"Без картинки: {', '.join(missing[:10])}")


if __name__ == "__main__":
    main()
