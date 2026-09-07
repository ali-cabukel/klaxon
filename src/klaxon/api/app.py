"""REST + Slack FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from klaxon.api.routers import issues as issues_router
from klaxon.api.routers import ops as ops_router
from klaxon.db.engine import dispose_engine, init_db
from klaxon.settings import get_settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    log.info("database ready")
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Klaxon",
        description="Incident management desk with Slack agent and MCP tools",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(issues_router.router)
    app.include_router(ops_router.router)

    from klaxon.slack.routes import register_slack_routes

    register_slack_routes(app)

    try:
        from klaxon.mcp.server import mcp

        # Expose MCP over SSE for external clients (Cursor, etc.).
        app.mount("/mcp", mcp.sse_app())
    except Exception as exc:  # pragma: no cover - optional surface
        log.warning("MCP HTTP mount skipped: %s", exc)

    @app.get("/healthz")
    async def healthz():
        settings = get_settings()
        return {
            "ok": True,
            "redirect_uri": settings.redirect_uri,
            "agent_enabled": settings.agent_enabled,
        }

    return app


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    host = "127.0.0.1"
    port = 3000
    uvicorn.run("klaxon.api.app:app", host=host, port=port, reload=False)
