"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from klaxon.db.engine import get_session_maker


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with get_session_maker()() as session:
        yield session
