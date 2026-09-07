"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Env before importing klaxon settings.
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("STATE_SECRET", "test-state-secret")
os.environ.setdefault("SLACK_CLIENT_ID", "123.456")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "")


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    from klaxon.settings import reset_settings

    reset_settings()
    from klaxon.db.engine import dispose_engine, reset_engine

    reset_engine()
    yield url
    # cleanup deferred to async fixtures


@pytest_asyncio.fixture
async def db_session(tmp_db: str):
    from klaxon.db.engine import dispose_engine, get_session_maker, init_db, reset_engine
    from klaxon.settings import reset_settings

    reset_settings()
    reset_engine()
    await init_db()
    async with get_session_maker()() as session:
        yield session
    await dispose_engine()
    reset_engine()
    reset_settings()


@pytest_asyncio.fixture
async def client(tmp_db: str):
    from klaxon.db.engine import dispose_engine, init_db, reset_engine
    from klaxon.settings import reset_settings

    reset_settings()
    reset_engine()
    await init_db()

    from klaxon.api.app import create_app

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    await dispose_engine()
    reset_engine()
    reset_settings()
