"""Догружает TACO — мусор, снятый в естественной среде.

Это единственный источник в нужном нам домене. Все остальные сняты либо
на конвейере полигона, либо на белом фоне в студии, а пользователь фотографирует
предмет на столе, на асфальте, в траве — там, где фон выразителен и норовит
перетянуть решение на себя. Разбор ошибок это подтвердил: банка в траве уходит
в «органику», комок фольги на картоне — в «бумагу».

Предыдущий опыт показал, что данные не из того домена делают только хуже:
TrashNet добавил почти две тысячи качественных студийных снимков и опустил
точность на независимом тесте на 1.2 пункта. Поэтому здесь берётся именно
уличная съёмка.

Берём снимки, где все размеченные объекты — одного класса, и оставляем кадр
целиком. Обрезать по рамке нельзя: получится студийный крупный план, то есть
ровно тот домен, которого у нас и так в избытке.

Требовать ровно один объект оказалось слишком строго: так отсеивалось 890
кадров из 1500 и оставалось 354 снимка. Три бутылки в траве — по-прежнему
однозначно «пластик», а вот бутылка рядом с окурком уже нет: окурок мы
ни к чему не сводим, и неизвестно, что на кадре главное. Поэтому условие
такое: все объекты сводятся к нашим классам и все — к одному и тому же.

    python -m prediction.fetch_taco
    python -m prediction.fetch_taco --per-class 200

Источник: https://huggingface.co/datasets/RandyHuynh5815/TACO-Reformatted-Full
"""

from __future__ import annotations

import argparse
import io
import json
import ssl
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "extra-classes"

DATASET = "RandyHuynh5815/TACO-Reformatted-Full"
PARQUET_URL = (
    "https://datasets-server.huggingface.co/parquet"
    f"?dataset={DATASET.replace('/', '%2F')}"
)

#: Номер категории TACO → класс нашей раскладки.
#: Пропущенные номера — то, что к нашим категориям не сводится однозначно
#: (окурки, верёвки, неопознанный мусор) либо спорно по материалу.
TACO_CLASSES: dict[int, str] = {
    0: "Metal",           # Aluminium foil
    1: "Battery",         # Battery
    4: "Plastic",         # Other plastic bottle
    5: "Plastic",         # Clear plastic bottle
    6: "Glass",           # Glass bottle
    7: "Plastic",         # Plastic bottle cap
    8: "Metal",           # Metal bottle cap
    9: "Glass",           # Broken glass
    10: "Metal",          # Food can
    11: "Metal",          # Aerosol
    12: "Metal",          # Drink can
    13: "Cardboard",      # Toilet tube
    14: "Cardboard",      # Other carton
    15: "Cardboard",      # Egg carton
    17: "Cardboard",      # Corrugated carton
    18: "Cardboard",      # Meal carton
    19: "Cardboard",      # Pizza box
    20: "Paper",          # Paper cup — ровно наш трудный случай
    21: "Plastic",        # Disposable plastic cup
    23: "Glass",          # Glass cup
    24: "Plastic",        # Other plastic cup
    25: "Food Organics",  # Food waste
    26: "Glass",          # Glass jar
    27: "Plastic",        # Plastic lid
    28: "Metal",          # Metal lid
    30: "Paper",          # Magazine paper
    32: "Paper",          # Wrapping paper
    33: "Paper",          # Normal paper
    34: "Paper",          # Paper bag
    36: "Plastic",        # Plastic film
    38: "Plastic",        # Garbage bag
    40: "Plastic",        # Single-use carrier bag
    41: "Plastic",        # Polypropylene bag
    44: "Plastic",        # Tupperware
    45: "Plastic",        # Disposable food container
    47: "Plastic",        # Other plastic container
    49: "Plastic",        # Plastic utensils
    50: "Metal",          # Pop tab
    52: "Metal",          # Scrap metal
    53: "Textile Trash",  # Shoe
    54: "Plastic",        # Squeezable tube
    55: "Plastic",        # Plastic straw
    56: "Paper",          # Paper straw
    # Ниже — то, что поначалу отсеивалось как «вне раскладки». Справочник
    # трактует эти предметы однозначно, так что кадры можно вернуть.
    16: "Plastic",        # Drink carton — тетрапак у нас числится в пластике
    22: "Plastic",        # Foam cup
    29: "Plastic",        # Other plastic
    31: "Paper",          # Tissues — салфетка у нас числится в бумаге
    37: "Plastic",        # Six pack rings
    39: "Plastic",        # Other plastic wrapper
    43: "Plastic",        # Spread tub
    46: "Plastic",        # Foam food container
    48: "Plastic",        # Plastic glooves
    51: "Textile Trash",  # Rope & strings
    57: "Plastic",        # Styrofoam piece — вспененный полистирол
}

#: Сознательно не сводим:
#:   58 Unlabeled litter — метка «мусор вообще», материал неизвестен;
#:   59 Cigarette — окурок занимает доли процента кадра, и метка на весь кадр
#:      научила бы модель решать по фону, то есть ровно тому, от чего лечим;
#:   42 Crisp packet, 2/3 blister pack — металлизированный композит,
#:      справочник их не разбирает, а угадывать материал на обучении вредно.

DEFAULT_PER_CLASS = 200


def _ssl_context() -> ssl.SSLContext:
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def main() -> None:
    parser = argparse.ArgumentParser(description="Догрузка TACO")
    parser.add_argument("--per-class", type=int, default=DEFAULT_PER_CLASS)
    args = parser.parse_args()

    context = _ssl_context()
    with urllib.request.urlopen(PARQUET_URL, context=context) as response:
        files = [f for f in json.load(response)["parquet_files"] if f["split"] == "train"]
    files.sort(key=lambda f: f["size"])

    import pyarrow.parquet as pq

    from prediction.train_classifier import _fingerprint

    saved: dict[str, int] = {}
    skipped_mixed = skipped_unknown = 0

    # Части по 340–545 МБ, всего 2.5 ГБ. Держим их на диске: подбор правил
    # разметки — дело нескольких заходов, и качать всё заново каждый раз глупо.
    cache = PROJECT_ROOT / ".cache" / "taco"
    cache.mkdir(parents=True, exist_ok=True)

    for entry in files:
        shard = cache / entry["filename"]
        if shard.exists():
            print(f"{entry['filename']} уже скачан")
            raw = shard.read_bytes()
        else:
            print(f"Скачиваем {entry['filename']} ({entry['size'] / 1048576:.0f} МБ)…")
            with urllib.request.urlopen(entry["url"], context=context) as response:
                raw = response.read()
            shard.write_bytes(raw)

        table = pq.read_table(io.BytesIO(raw))
        categories = table.column("categories").to_pylist()
        images = table.column("image").to_pylist()

        for index, (cats, image) in enumerate(zip(categories, images)):
            cats = list(cats or [])
            if not cats:
                skipped_unknown += 1
                continue

            mapped = {TACO_CLASSES.get(int(c)) for c in cats}
            # Хоть один объект вне нашей раскладки — кадр неоднозначен.
            if None in mapped:
                skipped_unknown += 1
                continue
            # Объекты разных классов — непонятно, что считать главным.
            if len(mapped) != 1:
                skipped_mixed += 1
                continue

            target_class = mapped.pop()
            if saved.get(target_class, 0) >= args.per_class:
                continue

            data = image.get("bytes") if isinstance(image, dict) else None
            if not data:
                continue

            directory = TARGET / target_class
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"taco_{entry['filename'][:4]}_{index}.jpg"

            # Снимки TACO по несколько мегабайт — ужимаем, обучение всё равно
            # работает с 224 пикселями, а место и время чтения экономятся.
            try:
                from PIL import Image

                with Image.open(io.BytesIO(data)) as picture:
                    picture = picture.convert("RGB")
                    picture.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                    picture.save(path, "JPEG", quality=85)
                _fingerprint(path)
            except Exception:  # noqa: BLE001
                path.unlink(missing_ok=True)
                continue

            saved[target_class] = saved.get(target_class, 0) + 1

    print(f"\nПропущено: {skipped_mixed} с объектами разных классов, "
          f"{skipped_unknown} с объектами вне раскладки")
    print("Добавлено:")
    for name, count in sorted(saved.items()):
        print(f"  {name:22} {count}")
    print(f"  всего {sum(saved.values())}")


if __name__ == "__main__":
    main()
