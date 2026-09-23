"""Async SQLAlchemy sessions; PostgreSQL or persistent local SQLite."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from app.config import Settings

# Imported for its side effect: the ORM classes must be registered on
# Base.metadata before create_all() or Alembic autogenerate can see them.
from app.db import tables as _tables  # noqa: F401
from app.db.base import Base
from app.logging_config import get_logger

log = get_logger(__name__)


class Database:
    def __init__(self, url: str, echo: bool = False) -> None:
        self.url = url
        kwargs = {"echo": echo, "future": True, "pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs.pop("pool_pre_ping")
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self.session_factory = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def create_all(self) -> None:
        """Create tables directly. Used by tests; production uses Alembic."""
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def healthy(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            log.warning("database.health_check_failed", error=str(exc))
            return False

    async def dispose(self) -> None:
        await self.engine.dispose()


def build_database(settings: Settings) -> Database:
    from pathlib import Path

    local_path = Path(__file__).resolve().parents[2] / "marle.sqlite3"
    url = settings.database_url or f"sqlite+aiosqlite:///{local_path}"
    return Database(url, echo=False)
