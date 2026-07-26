"""Обучение классификатора отходов на датасете RealWaste.

Почему классификация, а не детекция. RealWaste — набор снимков по папкам-классам,
рамок в нём нет, поэтому обучить на нём детектор нельзя. Приложению детекция и не
нужна: пользователь снимает один предмет крупно, вопрос стоит «из чего это»,
а не «где это на кадре».

Запуск:

    python -m prediction.train_classifier                 # обучение с настройками по умолчанию
    python -m prediction.train_classifier --epochs 40     # дольше и точнее
    python -m prediction.train_classifier --model yolov8m-cls.pt

Датасет ожидается в realwaste-main/RealWaste (папка на класс). Скрипт сам делит
его на train/val симлинками — 666 МБ снимков не копируются.

Результат кладётся в prediction/waste_classifier.pt — этот файл подхватывает
бэкенд при CLASSIFIER=ml.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Источники снимков: папка на класс. Одноимённые классы объединяются.
#: RealWaste лежит отдельно от дополнительных классов — у него своя лицензия.
DEFAULT_SOURCES = [
    PROJECT_ROOT / "realwaste-main" / "RealWaste",
    PROJECT_ROOT / "extra-classes",
]
#: Куда раскладывается train/val для ultralytics.
DEFAULT_SPLIT_DIR = PROJECT_ROOT / "datasets" / "realwaste"
#: Куда кладутся веса обученной модели.
DEFAULT_WEIGHTS = PROJECT_ROOT / "prediction" / "waste_classifier.pt"

#: Класс датасета → (категория справочника по-русски, название предмета).
#: Русские названия переводятся в id справочника в app/services/recognition/ml.py.
WASTE_CLASSES_RU: dict[str, tuple[str, str]] = {
    "Cardboard": ("бумага", "картон"),
    "Paper": ("бумага", "бумага"),
    "Glass": ("стекло", "стекло"),
    "Metal": ("металл", "металл"),
    "Plastic": ("пластик", "пластик"),
    "Food Organics": ("органика", "пищевые отходы"),
    "Vegetation": ("органика", "растительные остатки"),
    "Textile Trash": ("прочее", "текстиль"),
    "Miscellaneous Trash": ("прочее", "смешанные отходы"),
    # Особых отходов в RealWaste нет — класс приходит из extra-classes/.
    "Battery": ("особые отходы", "батарейка"),
}

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

#: Аугментация ultralytics для классификации.
#:
#: Осторожно: классификация принимает НЕ все параметры. В classify_augmentations
#: уходят только size, scale, hflip, vflip, erasing, auto_augment и hsv_*.
#: Знакомые по детекции degrees, translate, perspective, shear молча
#: игнорируются — задавать их бессмысленно.
#:
#: Более того, при заданном auto_augment ultralytics выбрасывает ColorJitter,
#: так что hsv_* тоже не доходят. Всё, что нам действительно нужно, добавляется
#: своими руками в attach_extra_augmentation.
AUGMENTATION = {
    # Предмет появляется в кадре и крупно, и мелко: прямо против случая,
    # когда он занимает малую часть снимка и решает фон.
    "scale": 0.35,
    "fliplr": 0.5,
    # У мусора на земле нет верха и низа, переворот не портит смысл.
    "flipud": 0.3,
    "erasing": 0.4,
}


def collect_classes(sources: list[Path]) -> dict[str, list[Path]]:
    """Собирает снимки по классам из всех источников.

    Одноимённые классы в разных источниках объединяются — так дополнительный
    класс можно положить рядом, не трогая исходный датасет.
    """
    classes: dict[str, list[Path]] = {}
    missing = [s for s in sources if not s.is_dir()]
    if len(missing) == len(sources):
        raise SystemExit(
            "Не найден ни один источник снимков: "
            + ", ".join(str(s) for s in sources)
            + "\nСкачайте RealWaste и положите в realwaste-main/RealWaste."
        )

    for source in sources:
        if not source.is_dir():
            continue
        for class_dir in sorted(p for p in source.iterdir() if p.is_dir()):
            images = [
                p for p in sorted(class_dir.iterdir())
                if p.suffix.lower() in IMAGE_SUFFIXES
            ]
            if images:
                classes.setdefault(class_dir.name, []).extend(images)
    return classes


def _fingerprint(path: Path) -> tuple[str, str]:
    """Отпечатки снимка: точный (по содержимому) и перцептивный (по картинке).

    Перцептивный ловит копии, пережатые или слегка изменённые: во внешнем
    датасете такие есть — часть снимков получена аугментацией исходных.
    """
    from PIL import Image

    data = path.read_bytes()
    exact = hashlib.md5(data).hexdigest()

    # 16×16 полутонов: достаточно подробно, чтобы не склеивать разные предметы.
    with Image.open(path) as im:
        small = im.convert("L").resize((16, 16), Image.Resampling.LANCZOS)
    pixels = list(small.getdata())
    mean = sum(pixels) / len(pixels)
    perceptual = "".join("1" if p > mean else "0" for p in pixels)
    return exact, perceptual


def group_duplicates(images: list[Path]) -> list[list[Path]]:
    """Объединяет копии одного снимка в группы, точные дубликаты выбрасывает.

    Группа целиком уезжает либо в train, либо в val. Если копии одного кадра
    разъедутся по разные стороны, валидационная точность окажется завышенной:
    модель будет отвечать на то, что уже видела на обучении.
    """
    seen_exact: set[str] = set()
    groups: dict[str, list[Path]] = {}

    for path in images:
        try:
            exact, perceptual = _fingerprint(path)
        except Exception:  # noqa: BLE001 - битый файл просто пропускаем
            continue
        if exact in seen_exact:
            continue
        seen_exact.add(exact)
        groups.setdefault(perceptual, []).append(path)

    return list(groups.values())


def build_split(
    sources: list[Path], target: Path, val_share: float, seed: int
) -> dict[str, int]:
    """Раскладывает снимки на train/val симлинками.

    Симлинки, а не копии: датасеты весят сотни мегабайт, дублировать их незачем.
    Разбиение детерминировано seed — повторный запуск даёт тот же split,
    иначе метрики между запусками несравнимы.

    Делим не отдельные снимки, а группы копий — см. group_duplicates.
    """
    classes = collect_classes(sources)
    if not classes:
        raise SystemExit("В источниках не нашлось изображений.")

    if target.exists():
        shutil.rmtree(target)

    counts: dict[str, int] = {}
    dropped = 0
    rng = random.Random(seed)

    for class_name, images in sorted(classes.items()):
        groups = group_duplicates(sorted(images))
        dropped += len(images) - sum(len(g) for g in groups)

        rng.shuffle(groups)
        cut = max(1, round(len(groups) * val_share))
        parts = {"val": groups[:cut], "train": groups[cut:]}

        kept = 0
        for split, split_groups in parts.items():
            split_dir = target / split / class_name
            split_dir.mkdir(parents=True, exist_ok=True)
            for group in split_groups:
                for image in group:
                    (split_dir / image.name).symlink_to(image.resolve())
                    kept += 1

        counts[class_name] = kept

    if dropped:
        print(f"Выброшено точных дубликатов: {dropped}")
    return counts


class RandomQuarterTurn:
    """Поворот на 0, 90, 180 или 270 градусов — с заданной вероятностью.

    Отдельно от RandomRotation, потому что решает другую задачу. Тот вертит
    на ±20° и учит терпимости к наклону; этот готовит к кадру, лежащему
    на боку целиком.

    Нужен по измеренной причине: на повёрнутом на прямой угол снимке точность
    падает с 92.50% до 82.08%, то есть на 10.4 пункта. Айфон пишет ориентацию
    в EXIF, и теперь мы её применяем, но снимок может прийти боком и без
    метаданных — после пересохранения, из мессенджера, со скриншота.

    torchvision такого преобразования не даёт: RandomRotation с углом 90
    вертит на любой угол между -90 и 90, а нам нужны ровно четверти оборота,
    иначе появятся пустые углы и картинка потеряет края.
    """

    def __init__(self, probability: float) -> None:
        self.probability = probability

    def __call__(self, image):  # noqa: ANN001
        import random

        from PIL import Image

        if random.random() >= self.probability:
            return image
        return image.transpose(
            random.choice(
                (Image.ROTATE_90, Image.ROTATE_180, Image.ROTATE_270)
            )
        )

    def __repr__(self) -> str:
        return f"RandomQuarterTurn(p={self.probability})"


def attach_extra_augmentation(
    model,
    grayscale: float,
    blur: float,
    rotate: float,
    jitter: float,
    quarter_turn: float = 0.0,
) -> None:
    """Добавляет то, чего набор ultralytics для классификации не даёт.

    Поворот. Параметр degrees классификацией игнорируется, а поворот нужен:
    предмет снимают под любым углом. RandAugment иногда поворачивает сам,
    но лишь когда выберет этот оператор из полутора десятков.

    Цвет. При заданном auto_augment ultralytics выбрасывает ColorJitter,
    поэтому hsv_* не доходят вовсе. А именно разброс насыщенности и яркости
    бьёт по главной беде: пока цвет доступен, модель решает по нему, и матовая
    белая бутылка уезжает в «бумагу» просто потому, что светлая.

    Обесцвечивание доводит эту мысль до конца: у части снимков цвета нет
    совсем, опереться остаётся только на форму и фактуру.

    Размытие делает модель терпимой к смазанным кадрам с телефона. Радиус
    небольшой: сильное размытие съело бы фактуру, а она и отличает бумагу
    от пластика.
    """

    def on_train_start(trainer) -> None:  # noqa: ANN001
        from torchvision import transforms as T

        dataset = trainer.train_loader.dataset
        operations = list(dataset.torch_transforms.transforms)

        extra = []
        # Четверть оборота — первой: остальные операции должны применяться
        # к уже повёрнутому кадру, иначе размытие и цвет лягут на другую
        # картинку, чем увидит модель.
        if quarter_turn > 0:
            extra.append(RandomQuarterTurn(quarter_turn))
        if rotate > 0:
            extra.append(T.RandomRotation(rotate, expand=False))
        if jitter > 0:
            extra.append(
                T.ColorJitter(brightness=jitter, contrast=jitter, saturation=jitter)
            )
        if grayscale > 0:
            extra.append(T.RandomGrayscale(p=grayscale))
        if blur > 0:
            extra.append(
                T.RandomApply([T.GaussianBlur(kernel_size=5, sigma=(0.1, 1.5))], p=blur)
            )
        if not extra:
            return

        # Вставляем до перевода в тензор: все операции работают с картинкой.
        index = next(
            (i for i, op in enumerate(operations) if op.__class__.__name__ == "ToTensor"),
            len(operations),
        )
        operations[index:index] = extra
        dataset.torch_transforms = T.Compose(operations)

        print("Добавлено к аугментации:")
        for op in extra:
            print(f"  {str(op).splitlines()[0][:90]}")

    model.add_callback("on_train_start", on_train_start)


def attach_progress(model, run_dir: Path, every: int = 5) -> None:
    """Пишет ход обучения в progress.json после каждых нескольких батчей.

    results.csv обновляется раз в эпоху, а эпоха идёт минуты — по нему не понять,
    туда ли всё движется. Здесь пишется бегущее среднее лосса по батчам текущей
    эпохи: если оно падает, направление верное, ждать конца эпохи не нужно.

    Пишем через временный файл: читатель не должен наткнуться на половину записи.
    """
    import json

    state = {"batch": 0}
    target = run_dir / "progress.json"

    def on_epoch_start(trainer) -> None:  # noqa: ANN001
        state["batch"] = 0

    def on_batch_end(trainer) -> None:  # noqa: ANN001
        state["batch"] += 1
        if state["batch"] % every and state["batch"] != 1:
            return

        losses = getattr(trainer, "tloss", None)
        if isinstance(losses, dict):
            loss = float(sum(float(v) for v in losses.values()))
        elif losses is not None:
            loss = float(losses)
        else:
            return

        payload = {
            "epoch": int(trainer.epoch) + 1,
            "epochs": int(trainer.epochs),
            "batch": state["batch"],
            "batches": len(trainer.train_loader),
            # Среднее по всем батчам эпохи, а не по последнему: отдельный батч
            "meanLoss": round(loss, 4),  # скачет и о направлении ничего не говорит.
        }
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            pass  # прогресс — вещь необязательная, ронять из-за него обучение незачем

    def on_train_end(trainer) -> None:  # noqa: ANN001
        target.unlink(missing_ok=True)

    model.add_callback("on_train_epoch_start", on_epoch_start)
    model.add_callback("on_train_batch_end", on_batch_end)
    model.add_callback("on_train_end", on_train_end)


class CategoryAwareLoss:
    """Штрафует за ошибку категории отдельно от ошибки класса.

    Мы обучаем на десять классов датасета, а показываем семь категорий
    справочника, и это не одно и то же. Обычная кросс-энтропия штрафует
    «Paper вместо Cardboard» ровно так же, как «Metal вместо Glass». Первая
    ошибка нам ничего не стоит — обе ведут в «бумагу», пользователь её даже
    не увидит. Вторая отправляет человека к неверному баку.

    Значит, обучение оптимизирует не то, что мы показываем. Здесь к обычным
    потерям добавляется второе слагаемое — та же кросс-энтропия, но по семи
    категориям. Вероятность категории собирается из вероятностей её классов
    (logsumexp по логитам — это и есть логарифм суммы вероятностей), поэтому
    десятиклассовая голова остаётся на месте: она нужна интерфейсу, который
    показывает не только категорию, но и предмет — «бутылка», «банка».

    Побочный, но важный эффект: «прочее» собрано из Textile Trash (1615) и
    Miscellaneous Trash (697), а «бумага» — из Paper и Cardboard. Путаница
    внутри пары становится бесплатной, то есть самый малочисленный класс
    датасета перестаёт быть отдельной мишенью и работает в паре с соседом.
    """

    def __init__(  # noqa: ANN001
        self,
        groups: list[list[int]],
        weights=None,
        strength: float = 1.0,
        smoothing: float = 0.0,
    ):
        self.groups = groups
        self.weights = weights
        self.strength = strength
        self.smoothing = smoothing
        self._category_of = None

    def __call__(self, preds, batch):  # noqa: ANN001
        import torch
        import torch.nn.functional as F  # noqa: N812

        logits = preds[1] if isinstance(preds, (list, tuple)) else preds
        target = batch["cls"]

        if self._category_of is None or self._category_of.device != logits.device:
            lookup = torch.empty(logits.shape[1], dtype=torch.long)
            for index, members in enumerate(self.groups):
                for member in members:
                    lookup[member] = index
            self._category_of = lookup.to(logits.device)
            if self.weights is not None:
                self.weights = self.weights.to(logits.device)

        fine = F.cross_entropy(
            logits,
            target,
            weight=self.weights,
            reduction="mean",
            label_smoothing=self.smoothing,
        )

        # При нулевом весе категорийное слагаемое не считаем вовсе: класс
        # используется и ради одного сглаживания меток, а logsumexp по группам
        # на каждом батче — не та цена, которую стоит платить впустую.
        if self.strength <= 0:
            return fine, {"loss": fine.detach()}

        # Логит категории — логарифм суммы вероятностей её классов.
        coarse_logits = torch.stack(
            [logits[:, members].logsumexp(dim=1) for members in self.groups], dim=1
        )
        coarse = F.cross_entropy(
            coarse_logits,
            self._category_of[target],
            reduction="mean",
            label_smoothing=self.smoothing,
        )

        loss = fine + self.strength * coarse
        return loss, {"loss": loss.detach()}


def attach_category_loss(
    model, strength: float, balance: float, smoothing: float = 0.0
) -> None:
    """Заменяет функцию потерь на привязанную к категориям.

    Порядок классов берём не из наших словарей, а у самого обучения: папки
    читаются по алфавиту, и полагаться на совпадение с нашим порядком нельзя —
    достаточно один раз добавить класс, чтобы всё молча разъехалось.

    `balance` выравнивает вклад редких классов: вес пропорционален
    (1/размер)^balance. При 0 веса равны, при 1 полностью компенсируют перекос.
    По умолчанию 0 — категорийного слагаемого обычно достаточно, а лишние
    ручки мешают понять, что именно дало эффект.
    """
    # Раньше здесь стоял ранний выход при strength <= 0 — и он молча съедал
    # сглаживание меток: оно живёт внутри CategoryAwareLoss, а обработчик
    # при выключенных категорийных потерях просто не навешивался. Флаг
    # --label-smoothing принимался, печатался в справке и не делал ничего.
    # Та же болезнь, что с аугментациями ultralytics: параметр есть, эффекта нет.
    if strength <= 0 and smoothing <= 0 and balance <= 0:
        return

    def on_train_start(trainer) -> None:  # noqa: ANN001
        import collections

        import torch

        from ultralytics.utils.torch_utils import unwrap_model

        names = trainer.data["names"]  # {индекс: имя класса}
        order = [names[i] for i in range(len(names))]

        unknown = [n for n in order if n not in WASTE_CLASSES_RU]
        if unknown:
            raise SystemExit(f"Классы без категории: {unknown}")

        grouped: dict[str, list[int]] = collections.defaultdict(list)
        for index, name in enumerate(order):
            grouped[WASTE_CLASSES_RU[name][0]].append(index)
        groups = [grouped[key] for key in sorted(grouped)]

        weights = None
        if balance > 0:
            counts = collections.Counter()
            for _, label in trainer.train_loader.dataset.samples:
                counts[int(label)] += 1
            raw = torch.tensor(
                [(1.0 / max(counts[i], 1)) ** balance for i in range(len(order))],
                dtype=torch.float32,
            )
            weights = raw / raw.mean()

        unwrap_model(trainer.model).criterion = CategoryAwareLoss(
            groups, weights, strength, smoothing
        )

        # Печатаем ровно то, что включено. Сообщение про категории при нулевом
        # весе сбивало бы с толку — а именно так и теряются молча выключенные
        # настройки: в логе написано одно, считается другое.
        if strength > 0:
            readable = ", ".join(
                f"{key} ({len(grouped[key])})" for key in sorted(grouped)
            )
            print(f"Потери привязаны к категориям ({strength}): {readable}")
        if smoothing > 0:
            print(f"Сглаживание меток: {smoothing}")
        if weights is not None:
            print("Веса классов: " + ", ".join(
                f"{order[i]} {float(weights[i]):.2f}" for i in range(len(order))
            ))

    model.add_callback("on_train_start", on_train_start)


def attach_category_checkpoint(model, run_dir: Path) -> None:
    """Сохраняет веса лучшей эпохи по точности категорий, а не классов.

    Ultralytics выбирает лучшую эпоху по top-1 среди десяти классов. Нам важна
    доля верных категорий, а это другое число: эпоха может выиграть на
    различении Paper и Cardboard и проиграть там, где для человека всё решается.

    Считаем по ответам, которые валидатор уже сложил, — лишнего прохода нет.
    """
    best = {"score": -1.0}

    def on_fit_epoch_end(trainer) -> None:  # noqa: ANN001
        import shutil as _shutil

        import torch

        validator = getattr(trainer, "validator", None)
        if not validator or not getattr(validator, "pred", None):
            return

        names = trainer.data["names"]
        category_of = {
            index: WASTE_CLASSES_RU[names[index]][0]
            for index in range(len(names))
            if names[index] in WASTE_CLASSES_RU
        }

        predicted = torch.cat([p[:, 0] for p in validator.pred]).tolist()
        actual = torch.cat(validator.targets).tolist()
        hits = sum(
            category_of.get(p) == category_of.get(a) for p, a in zip(predicted, actual)
        )
        score = hits / max(len(actual), 1)

        source = run_dir / "weights" / "last.pt"
        if score > best["score"] and source.exists():
            best["score"] = score
            _shutil.copy2(source, run_dir / "weights" / "best_category.pt")
        print(f"      точность категорий: {score:.4f} (лучшая {best['score']:.4f})")

    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)


def pick_device() -> str:
    import torch

    if torch.cuda.is_available():
        return "0"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def enable_half_precision(device: str) -> bool:
    """Включает счёт в bfloat16 на видеоядре Apple. True, если получилось.

    Ultralytics принимает amp=True, пишет его в лог — и на MPS не применяет:
    внутри вызывается autocast(self.amp) без второго аргумента, а по умолчанию
    там device="cuda". Контекст для чужого устройства над тензорами MPS
    не делает ничего, так что счёт молча остаётся в полной точности.

    Замер на M4, yolov8m, батч 48: 37 кадров/с в fp32 против 42 в bfloat16.
    Батч на скорость не влияет вовсе (34–36 кадров/с при 48, 96 и 160) —
    видеоядро загружено полностью уже при 48, поэтому увеличивать его
    или число воркеров бессмысленно.

    Берём bfloat16, а не float16: у него тот же диапазон, что у float32,
    поэтому не нужно масштабировать градиенты. А масштабировать их и нечем —
    ultralytics создаёт GradScaler для CUDA, и без неё он сам себя отключает.
    Скорость при этом одинаковая: 42 кадра/с у обоих.
    """
    if device != "mps":
        return False

    import torch

    from ultralytics.engine import trainer as trainer_module

    def mps_autocast(enabled, device: str = "mps"):  # noqa: ANN001, ARG001
        return torch.autocast("mps", dtype=torch.bfloat16, enabled=bool(enabled))

    trainer_module.autocast = mps_autocast
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Обучение классификатора отходов на RealWaste")
    parser.add_argument(
        "--source", type=Path, nargs="+", default=DEFAULT_SOURCES,
        help="папки с классами (одноимённые классы объединяются)",
    )
    parser.add_argument("--split-dir", type=Path, default=DEFAULT_SPLIT_DIR)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS, help="куда сохранить модель")
    parser.add_argument("--model", default="yolov8s-cls.pt", help="базовая модель")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--val-share", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default=None, help="cpu, mps или номер GPU")
    parser.add_argument(
        "--rotate",
        type=float,
        default=20.0,
        help="максимальный угол поворота в градусах (0 — выключить)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.5,
        help="разброс яркости, контраста и насыщенности (0 — выключить)",
    )
    parser.add_argument(
        "--grayscale",
        type=float,
        default=0.15,
        help="доля снимков, обесцвечиваемых при обучении (0 — выключить)",
    )
    parser.add_argument(
        "--blur",
        type=float,
        default=0.15,
        help="доля снимков, которые слегка размываются (0 — выключить)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "процессы загрузки данных. На MPS ultralytics принудительно ставит 0, "
            "и загрузка идёт последовательно с вычислением: у нас это ~55 с из "
            "219 с эпохи. Значение >0 возвращает параллельную загрузку — эпоха "
            "укорачивается примерно на четверть"
        ),
    )
    parser.add_argument(
        "--quarter-turn",
        type=float,
        default=0.0,
        help=(
            "вероятность повернуть снимок на 90, 180 или 270 градусов. "
            "На повёрнутом кадре точность падает на 10.4 пункта, а прийти он "
            "может боком и без метаданных — из мессенджера, со скриншота"
        ),
    )
    parser.add_argument(
        "--category-loss",
        type=float,
        default=1.0,
        help=(
            "вес второго слагаемого потерь — ошибки категории справочника. "
            "0 отключает и возвращает обычное обучение по десяти классам"
        ),
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=0.0,
        help=(
            "насколько выравнивать вклад редких классов: вес ~ (1/размер)^balance. "
            "0 — веса равны, 1 — перекос компенсируется полностью"
        ),
    )
    parser.add_argument(
        "--label-smoothing",
        type=float,
        default=0.0,
        help=(
            "сглаживание меток: вместо «это на 100%% бумага» модель учится на "
            "«это бумага на 90%%, остальное поровну». Лечит уверенные ошибки — "
            "живой случай: стакан определился металлом с уверенностью 89%%"
        ),
    )
    parser.add_argument(
        "--full-precision",
        action="store_true",
        help=(
            "считать в float32. По умолчанию на видеоядре Apple включается "
            "bfloat16: он быстрее примерно на 14%% и на точность не влияет — "
            "диапазон чисел тот же, веса всё равно хранятся в float32"
        ),
    )
    args = parser.parse_args()

    print("Готовим разбиение…")
    counts = build_split(list(args.source), args.split_dir, args.val_share, args.seed)
    total = sum(counts.values())
    print(f"Классов: {len(counts)}, снимков: {total}")
    for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        category, obj = WASTE_CLASSES_RU.get(name, ("?", "?"))
        print(f"  {name:22} {count:5}  → {category} / {obj}")

    unmapped = set(counts) - set(WASTE_CLASSES_RU)
    if unmapped:
        raise SystemExit(
            f"В датасете есть классы без соответствия категории: {sorted(unmapped)}. "
            "Добавьте их в WASTE_CLASSES_RU."
        )

    device = args.device or pick_device()
    precision = "float32"
    if not args.full_precision and enable_half_precision(device):
        precision = "bfloat16"
    print(
        f"\nОбучаем {args.model} на {device} ({precision}), "
        f"{args.epochs} эпох, {args.imgsz}px…\n"
    )

    from ultralytics import YOLO

    model = YOLO(args.model)
    attach_extra_augmentation(
        model, args.grayscale, args.blur, args.rotate, args.jitter, args.quarter_turn
    )
    attach_category_loss(
        model, args.category_loss, args.balance, args.label_smoothing
    )
    attach_category_checkpoint(model, PROJECT_ROOT / "runs" / "realwaste")
    attach_progress(model, PROJECT_ROOT / "runs" / "realwaste")
    model.train(
        data=str(args.split_dir),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=device,
        seed=args.seed,
        project=str(PROJECT_ROOT / "runs"),
        name="realwaste",
        exist_ok=True,
        verbose=True,
        plots=False,
        **AUGMENTATION,
    )

    # Берём лучшую по категориям эпоху, если она посчиталась: ultralytics выбирает
    # лучшую по top-1 среди десяти классов, а нам важна доля верных категорий.
    weights_dir = PROJECT_ROOT / "runs" / "realwaste" / "weights"
    best = weights_dir / "best_category.pt"
    if not best.exists():
        best = weights_dir / "best.pt"
    else:
        print(f"Берём лучшую эпоху по точности категорий: {best.name}")
    if not best.exists():
        raise SystemExit(f"Обучение прошло, но веса не найдены: {best}")

    weights = args.weights if args.weights.is_absolute() else PROJECT_ROOT / args.weights
    weights.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, weights)
    # relative_to падает на путях вне корня проекта, а --weights может быть любым.
    try:
        shown = weights.relative_to(PROJECT_ROOT)
    except ValueError:
        shown = weights
    print(f"\nМодель сохранена: {shown}")

    # Сводка по эпохам — её отдаёт бэкенд и показывает интерфейс,
    # чтобы за точностью и потерями не нужно было лезть в логи обучения.
    from prediction.metrics import format_table, save_metrics

    summary = save_metrics(
        run_dir=PROJECT_ROOT / "runs" / "realwaste", classes=sorted(counts)
    )
    print()
    print(format_table(summary))

    validation = YOLO(args.weights).val(data=str(args.split_dir), device=device, verbose=False)
    print(f"\nТочность top-1: {validation.top1:.3f}   top-5: {validation.top5:.3f}")


if __name__ == "__main__":
    main()
