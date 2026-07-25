from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import settings
from app.core.deps import DeviceDep, SessionDep
from app.db.models import Category, Correction, Scan, ensure_utc
from app.schemas.category import CategoryBase
from app.schemas.scan import CorrectionRequest, ManualScanRequest, ScanResult
from app.services.gamification import award_points
from app.services.recognition.base import Prediction
from app.services.recognition.registry import get_classifier

router = APIRouter(prefix="/scan", tags=["scan"])

_CHUNK = 64 * 1024

UNRECOGNIZED_MESSAGE = (
    "Предмет на фото не похож ни на один известный тип отхода. "
    "Снимите один предмет крупно на ровном фоне — или выберите категорию вручную."
)


async def _read_image(file: UploadFile) -> bytes:
    """Читает загруженное фото в память с проверкой типа и размера.

    Файл нигде не сохраняется: после ответа байты просто уходят в сборщик мусора.
    """
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Нужен файл изображения: JPG, PNG или WEBP.",
        )

    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"Файл больше {settings.max_upload_bytes // (1024 * 1024)} МБ.",
            )
        chunks.append(chunk)

    if not size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл пустой.",
        )
    return b"".join(chunks)


async def _require_category(session: SessionDep, category_id: str) -> Category:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Категория {category_id!r} не найдена.",
        )
    return category


def _to_result(
    scan: Scan,
    category: Category,
    total_points: int,
    prediction: Prediction | None = None,
) -> ScanResult:
    return ScanResult(
        scan_id=scan.id,
        object_name=scan.object_name,
        confidence=scan.confidence,
        is_manual=scan.is_manual,
        category=CategoryBase.model_validate(category),
        boxes=prediction.boxes if prediction else [],
        tech=prediction.tech if prediction else [],
        points_awarded=scan.points_awarded,
        total_points=total_points,
        created_at=ensure_utc(scan.created_at),
    )


@router.post("", response_model=ScanResult, status_code=status.HTTP_201_CREATED)
async def scan_image(
    session: SessionDep,
    device: DeviceDep,
    file: UploadFile = File(description="Фото предмета: JPG, PNG или WEBP"),
) -> ScanResult:
    """Распознаёт предмет на фото и записывает сканирование в историю."""
    image = await _read_image(file)

    prediction = await get_classifier().predict(image, file.content_type or "")
    if prediction is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=UNRECOGNIZED_MESSAGE,
        )

    category = await _require_category(session, prediction.category_id)
    awarded = await award_points(session, device, category.id)

    scan = Scan(
        device_id=device.id,
        category_id=category.id,
        object_name=prediction.object_name,
        confidence=prediction.confidence,
        is_manual=False,
        points_awarded=awarded,
    )
    session.add(scan)
    await session.commit()

    return _to_result(scan, category, device.points, prediction)


@router.post("/manual", response_model=ScanResult, status_code=status.HTTP_201_CREATED)
async def scan_manual(
    payload: ManualScanRequest,
    session: SessionDep,
    device: DeviceDep,
) -> ScanResult:
    """Пользователь выбрал тип отхода руками — например, когда распознавание не сработало."""
    category = await _require_category(session, payload.category_id)
    awarded = await award_points(session, device, category.id)

    scan = Scan(
        device_id=device.id,
        category_id=category.id,
        object_name="указано вручную",
        confidence=1.0,
        is_manual=True,
        points_awarded=awarded,
    )
    session.add(scan)
    await session.commit()

    return _to_result(scan, category, device.points)


@router.post("/{scan_id}/correct", response_model=ScanResult)
async def correct_scan(
    scan_id: str,
    payload: CorrectionRequest,
    session: SessionDep,
    device: DeviceDep,
) -> ScanResult:
    """«Модель ошиблась? Исправьте» — переносит скан в верную категорию.

    Очки не пересчитываются: исправление уточняет уже начисленный результат,
    а не добавляет новое сканирование.
    """
    scan = await session.get(Scan, scan_id)
    if scan is None or scan.device_id != device.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сканирование не найдено.",
        )

    category = await _require_category(session, payload.category_id)

    session.add(
        Correction(
            device_id=device.id,
            scan_id=scan.id,
            predicted_category_id=scan.category_id,
            corrected_category_id=category.id,
        )
    )
    scan.category_id = category.id
    scan.is_manual = True
    scan.confidence = 1.0
    await session.commit()

    return _to_result(scan, category, device.points)
