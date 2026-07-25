"""Рисует QR-код на репозиторий — для слайда и раздатки.

Цвета фирменные, но с оговоркой: контраст между тёмным и светлым модулем должен
оставаться высоким, иначе камера телефона перестанет читать код под углом или
при плохом свете. Поэтому берём самый тёмный зелёный и почти белый фон.

    python docs/make_qr.py
    python docs/make_qr.py --url https://example.com --out docs/qr.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_URL = "https://github.com/DanilPr0Z/EcoScaner"
DEFAULT_OUT = PROJECT_ROOT / "docs" / "qr-repo.png"

DARK = "#31572C"
LIGHT = "#FAF9F6"


def main() -> None:
    parser = argparse.ArgumentParser(description="QR-код на репозиторий")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--box", type=int, default=16, help="размер модуля в пикселях")
    args = parser.parse_args()

    import qrcode
    from qrcode.constants import ERROR_CORRECT_H

    code = qrcode.QRCode(
        version=None,  # подберётся под длину ссылки
        # Высокий уровень коррекции: код останется читаемым, даже если его
        # напечатают мелко или частично перекроют.
        error_correction=ERROR_CORRECT_H,
        box_size=args.box,
        border=4,  # обязательная «тихая зона», без неё камеры не находят код
    )
    code.add_data(args.url)
    code.make(fit=True)

    image = code.make_image(fill_color=DARK, back_color=LIGHT)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)

    size = image.size[0]
    print(f"{args.url}\n→ {args.out.relative_to(PROJECT_ROOT)}  {size}×{size} px")


if __name__ == "__main__":
    main()
