from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, future=True)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # noqa: ANN001
        """Настройки SQLite под параллельные запросы.

        WAL — потому что last_seen_at пишется на каждый запрос, а фронт ходит
        в API параллельно: в обычном режиме журнала читатели и писатель блокируют
        друг друга. busy_timeout даёт короткому конфликту разойтись самому,
        а не падать с «database is locked». Внешние ключи в SQLite по умолчанию
        выключены, поэтому включаем явно.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI-зависимость: сессия на запрос."""
    async with AsyncSessionLocal() as session:
        yield session
