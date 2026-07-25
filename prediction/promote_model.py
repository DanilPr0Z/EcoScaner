"""Заменяет рабочую модель новой — но только если та действительно лучше.

Обучение кладёт результат в отдельный файл, а не поверх рабочего. Прежде чем
подменить, обе модели прогоняются по независимому тесту — снимкам из источника,
которого не было в обучении. Побеждает та, что точнее по категориям справочника:
пользователю важен бак, а не класс модели.

Так исключается главный риск переобучения вслепую: цифры на валидации могут
вырасти, а на настоящих фотографиях модель станет хуже. Если это случилось,
рабочая модель остаётся прежней.

    python -m prediction.promote_model
    python -m prediction.promote_model --force   # заменить, не спрашивая метрик
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURRENT = PROJECT_ROOT / "prediction" / "waste_classifier.pt"
CANDIDATE = PROJECT_ROOT / "prediction" / "waste_classifier.candidate.pt"
TESTSET = PROJECT_ROOT / "testset"

#: Насколько новая модель должна быть лучше, чтобы менять рабочую.
#: Небольшой запас нужен, потому что разница в один-два снимка на выборке
#: в несколько сотен — это шум, а не улучшение.
MIN_GAIN = 0.005


def accuracy(weights: Path) -> tuple[float, dict[str, tuple[int, int]]]:
    """Точность по категориям справочника на независимом тесте."""
    from ultralytics import YOLO

    from prediction.train_classifier import WASTE_CLASSES_RU

    category_of = {name: ru[0] for name, ru in WASTE_CLASSES_RU.items()}
    model = YOLO(str(weights))

    hits = total = 0
    per_category: dict[str, tuple[int, int]] = {}

    for class_dir in sorted(p for p in TESTSET.iterdir() if p.is_dir()):
        expected = category_of.get(class_dir.name)
        if expected is None:
            continue
        images = [str(p) for p in sorted(class_dir.iterdir()) if p.is_file()]
        if not images:
            continue

        good = 0
        for result in model.predict(images, verbose=False):
            got = category_of.get(result.names[int(result.probs.top1)], "?")
            good += got == expected
        hits += good
        total += len(images)
        was_hits, was_total = per_category.get(expected, (0, 0))
        per_category[expected] = (was_hits + good, was_total + len(images))

    return (hits / total if total else 0.0), per_category


def main() -> None:
    parser = argparse.ArgumentParser(description="Замена рабочей модели")
    parser.add_argument("--force", action="store_true", help="заменить без сравнения")
    args = parser.parse_args()

    if not CANDIDATE.exists():
        raise SystemExit(f"Нет обученной модели-кандидата: {CANDIDATE.name}")

    if args.force or not CURRENT.exists():
        shutil.copy2(CANDIDATE, CURRENT)
        print(f"Рабочая модель заменена: {CURRENT.name}")
        return

    if not TESTSET.is_dir():
        raise SystemExit(
            "Нет независимого теста. Соберите его: python -m prediction.build_testset"
        )

    print("Считаем текущую модель…")
    current_score, current_by_category = accuracy(CURRENT)
    print("Считаем кандидата…")
    candidate_score, candidate_by_category = accuracy(CANDIDATE)

    print(f"\n{'категория':<16}{'текущая':>10}{'кандидат':>12}{'разница':>10}")
    print("-" * 48)
    for category in sorted(set(current_by_category) | set(candidate_by_category)):
        a_hits, a_total = current_by_category.get(category, (0, 0))
        b_hits, b_total = candidate_by_category.get(category, (0, 0))
        a = a_hits / a_total if a_total else 0
        b = b_hits / b_total if b_total else 0
        print(f"{category:<16}{a:>9.1%}{b:>12.1%}{(b - a) * 100:>+9.1f}")
    print("-" * 48)
    print(f"{'ИТОГО':<16}{current_score:>9.1%}{candidate_score:>12.1%}"
          f"{(candidate_score - current_score) * 100:>+9.1f}")

    if candidate_score >= current_score + MIN_GAIN:
        shutil.copy2(CANDIDATE, CURRENT)
        print(f"\nКандидат лучше — рабочая модель заменена.")
        print("Перезапустите бэкенд, чтобы он подхватил новые веса.")
    elif candidate_score >= current_score:
        print(f"\nРазница меньше {MIN_GAIN:.1%} — это шум, а не улучшение.")
        print("Рабочая модель оставлена прежней. Заменить принудительно: --force")
    else:
        print("\nКандидат хуже. Рабочая модель оставлена прежней.")


if __name__ == "__main__":
    main()
