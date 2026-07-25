from __future__ import annotations

import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Device, utcnow
from app.db.session import get_session

DEVICE_ID_HEADER = "X-Device-Id"
_DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_device(
    session: SessionDep,
    x_device_id: Annotated[str | None, Header(alias=DEVICE_ID_HEADER)] = None,
) -> Device:
    """Анонимный пользователь по заголовку X-Device-Id.

    Фронт один раз генерирует UUID (crypto.randomUUID()), хранит у себя и шлёт
    с каждым запросом. При первом визите заводим запись.
    """
    if not x_device_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Не передан заголовок {DEVICE_ID_HEADER}.",
        )
    if not _DEVICE_ID_RE.match(x_device_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Некорректный {DEVICE_ID_HEADER}: ожидается UUID.",
        )

    device = await session.get(Device, x_device_id)
    if device is None:
        device = Device(id=x_device_id)
        session.add(device)
        try:
            await session.flush()
        except IntegrityError:
            # Фронт шлёт запросы параллельно (профиль и история грузятся разом),
            # поэтому при первом визите два из них могут одновременно не найти
            # устройство и одновременно попытаться его создать. Кто-то один
            # успевает первым — второй просто перечитывает запись.
            await session.rollback()
            device = await session.get(Device, x_device_id)
            if device is None:
                raise

    device.last_seen_at = utcnow()
    await session.commit()
    return device


DeviceDep = Annotated[Device, Depends(get_device)]
