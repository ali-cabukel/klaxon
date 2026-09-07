"""Register Slack HTTP routes on the FastAPI app."""

from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from klaxon.slack.handlers import commands as command_handlers
from klaxon.slack.handlers import events as event_handlers
from klaxon.slack.handlers import interactivity as interactivity_handlers
from klaxon.slack.oauth import build_install_url, exchange_code, verify_state
from klaxon.slack.security import verify_slack_request
from klaxon.slack.store import get_installation_store

log = logging.getLogger(__name__)


def _form(raw: bytes) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(raw.decode()).items()}


def register_slack_routes(app: FastAPI) -> None:
    @app.get("/slack/install")
    async def install() -> RedirectResponse:
        return RedirectResponse(build_install_url())

    @app.get("/slack/oauth/callback", response_class=HTMLResponse)
    async def oauth_callback(
        code: str = "", state: str = "", error: str = ""
    ) -> HTMLResponse:
        if error:
            return HTMLResponse(
                f"<h1>Install cancelled</h1><p>{error}</p>", status_code=400
            )
        if not verify_state(state):
            return HTMLResponse("<h1>Invalid or expired state</h1>", status_code=400)
        installation = await exchange_code(code)
        get_installation_store().save(installation)
        log.info(
            "installed on team %s (%s)", installation.team_name, installation.team_id
        )
        return HTMLResponse(
            f"<h1>Installed in {installation.team_name}</h1>"
            "<p>You can close this window and return to Slack.</p>"
        )

    @app.post("/slack/events")
    async def events(
        request: Request,
        background: BackgroundTasks,
        raw: bytes = Depends(verify_slack_request),
    ):
        body = json.loads(raw)
        if body.get("type") == "url_verification":
            return {"challenge": body["challenge"]}
        if request.headers.get("X-Slack-Retry-Reason") == "http_timeout":
            return JSONResponse({"ok": True})
        if body.get("type") == "event_callback":
            event_id = body.get("event_id", "")
            if event_handlers.already_processed(event_id):
                return JSONResponse({"ok": True})
            background.add_task(
                event_handlers.handle_event, body, get_installation_store()
            )
        return JSONResponse({"ok": True})

    @app.post("/slack/commands")
    async def slash_commands(raw: bytes = Depends(verify_slack_request)):
        payload = _form(raw)
        log.info("command %s from %s", payload.get("command"), payload.get("user_id"))
        response = await command_handlers.dispatch(payload)
        return JSONResponse(response or {})

    @app.post("/slack/interactivity")
    async def interactivity(raw: bytes = Depends(verify_slack_request)):
        form = _form(raw)
        payload = json.loads(form["payload"])
        response = await interactivity_handlers.handle_interaction(
            payload, get_installation_store()
        )
        return JSONResponse(response or {})
