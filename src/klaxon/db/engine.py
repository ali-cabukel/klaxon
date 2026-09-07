"""Shared async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from klaxon.db.models import Base
from klaxon.db.session import create_engine, create_session_factory

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine()
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _session_maker
    if _session_maker is None:
        _session_maker = create_session_factory(get_engine())
    return _session_maker


async def get_async_session() -> AsyncGenerator[AsyncSession]:
    async with get_session_maker()() as session:
        yield session


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    global _engine, _session_maker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_maker = None


def reset_engine() -> None:
    """Reset cached engine (for tests). Caller must dispose first if needed."""
    global _engine, _session_maker
    _engine = None
    _session_maker = None
