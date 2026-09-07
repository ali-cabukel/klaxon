"""Slack OAuth v2 install flow."""

from __future__ import annotations

import time
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from klaxon.settings import Settings, get_settings
from klaxon.slack.store import InstallationRecord, InstallationStore

SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_API = "https://slack.com/api"
STATE_MAX_AGE = 600


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.state_secret, salt="slack-oauth-state")


def build_install_url(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    state = _serializer(settings).dumps({"ts": int(time.time())})
    params = {
        "client_id": settings.slack_client_id,
        "scope": ",".join(settings.bot_scopes),
        "user_scope": ",".join(settings.user_scopes),
        "redirect_uri": settings.redirect_uri,
        "state": state,
    }
    return f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}"


def verify_state(state: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    try:
        _serializer(settings).loads(state, max_age=STATE_MAX_AGE)
        return True
    except (BadSignature, SignatureExpired):
        return False


async def exchange_code(code: str, settings: Settings | None = None) -> InstallationRecord:
    settings = settings or get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SLACK_API}/oauth.v2.access",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "code": code,
                "redirect_uri": settings.redirect_uri,
            },
        )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Slack OAuth failed: {payload.get('error')}")

    team = payload.get("team") or {}
    enterprise = payload.get("enterprise") or {}
    authed_user = payload.get("authed_user") or {}
    expires_in = payload.get("expires_in")

    return InstallationRecord(
        team_id=team.get("id", ""),
        team_name=team.get("name", ""),
        bot_token=payload.get("access_token", ""),
        bot_user_id=payload.get("bot_user_id", ""),
        scopes=payload.get("scope", ""),
        installer_user_id=authed_user.get("id", ""),
        refresh_token=payload.get("refresh_token"),
        expires_at=int(time.time()) + expires_in if expires_in else None,
        enterprise_id=enterprise.get("id"),
    )


async def refresh_installation(
    installation: InstallationRecord, settings: Settings | None = None
) -> InstallationRecord:
    if not installation.refresh_token:
        return installation
    settings = settings or get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{SLACK_API}/oauth.v2.exchange",
            data={
                "client_id": settings.slack_client_id,
                "client_secret": settings.slack_client_secret,
                "refresh_token": installation.refresh_token,
            },
        )
    payload = resp.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Token refresh failed: {payload.get('error')}")

    installation.bot_token = payload.get("access_token", installation.bot_token)
    installation.refresh_token = payload.get(
        "refresh_token", installation.refresh_token
    )
    if payload.get("expires_in"):
        installation.expires_at = int(time.time()) + payload["expires_in"]
    return installation


async def ensure_fresh_token(
    store: InstallationStore, team_id: str
) -> InstallationRecord | None:
    installation = store.find(team_id)
    if installation is None:
        return None
    if installation.is_expiring:
        installation = await refresh_installation(installation)
        store.save(installation)
    return installation
