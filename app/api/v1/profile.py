from __future__ import annotations

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import delete, func, select

from app.core.deps import DeviceDep, SessionDep
from app.db.models import Category, Correction, Scan, ensure_utc
from app.schemas.profile import HistoryEntry, HistoryOut, ProfileOut
from app.services.gamification import build_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(session: SessionDep, device: DeviceDep) -> ProfileOut:
    """Очки, число сканирований, серия дней, распределение по бакам и бейджи."""
    return await build_profile(session, device)


@router.get("/history", response_model=HistoryOut)
async def get_history(
    session: SessionDep,
    device: DeviceDep,
    limit: int = Query(default=12, ge=1, le=100),
) -> HistoryOut:
    total = await session.scalar(
        select(func.count()).select_from(Scan).where(Scan.device_id == device.id)
    )
    rows = (
        await session.execute(
            select(Scan, Category)
            .join(Category, Category.id == Scan.category_id)
            .where(Scan.device_id == device.id)
            .order_by(Scan.created_at.desc())
            .limit(limit)
        )
    ).all()

    return HistoryOut(
        total=total or 0,
        items=[
            HistoryEntry(
                id=scan.id,
                category_id=category.id,
                category_name=category.name,
                category_color=category.color,
                object_name=scan.object_name,
                confidence=scan.confidence,
                is_manual=scan.is_manual,
                created_at=ensure_utc(scan.created_at),
            )
            for scan, category in rows
        ],
    )


@router.delete("/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(session: SessionDep, device: DeviceDep) -> Response:
    """Кнопка «Очистить» на экране профиля: сбрасывает историю и очки."""
    await session.execute(delete(Correction).where(Correction.device_id == device.id))
    await session.execute(delete(Scan).where(Scan.device_id == device.id))
    device.points = 0
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
