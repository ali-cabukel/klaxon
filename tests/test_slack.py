"""Slack plumbing tests (no network)."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("SLACK_SIGNING_SECRET", "test-signing-secret")
os.environ.setdefault("STATE_SECRET", "test-state-secret")
os.environ.setdefault("SLACK_CLIENT_ID", "123.456")

from klaxon.agent.service import to_mrkdwn  # noqa: E402
from klaxon.slack.handlers.commands import dispatch, parse_args  # noqa: E402
from klaxon.slack.handlers.events import already_processed, strip_mention  # noqa: E402
from klaxon.slack.oauth import build_install_url, verify_state  # noqa: E402
from klaxon.slack.security import compute_signature, is_valid_signature  # noqa: E402

SECRET = "test-signing-secret"


def test_signature_roundtrip():
    ts = str(int(time.time()))
    body = b"token=abc&command=%2Fping"
    sig = compute_signature(SECRET, ts, body)
    assert is_valid_signature(SECRET, ts, body, sig)


def test_signature_rejects_tampered_body():
    ts = str(int(time.time()))
    sig = compute_signature(SECRET, ts, b"original")
    assert not is_valid_signature(SECRET, ts, b"tampered", sig)


def test_signature_rejects_replay():
    old = str(int(time.time()) - 3600)
    body = b"x=1"
    sig = compute_signature(SECRET, old, body)
    assert not is_valid_signature(SECRET, old, body, sig)


def test_install_url_contains_scopes_and_state():
    from klaxon.settings import reset_settings

    reset_settings()
    url = build_install_url()
    assert "client_id=123.456" in url
    assert "scope=" in url
    state = url.split("state=")[1].split("&")[0]
    assert verify_state(state)


def test_state_rejects_forgery():
    assert not verify_state("not-a-real-state")


def test_strip_mention():
    assert strip_mention("<@U0123ABC> summarise this") == "summarise this"


def test_dedupe():
    assert not already_processed("EvKlaxon1")
    assert already_processed("EvKlaxon1")


def test_parse_args():
    assert parse_args('deploy "my app" --force') == ["deploy", "my app", "--force"]


def test_mrkdwn_conversion():
    assert to_mrkdwn("**bold**") == "*bold*"
    assert to_mrkdwn("[docs](https://x.com)") == "<https://x.com|docs>"
    assert to_mrkdwn("## Heading") == "*Heading*"


@pytest.mark.asyncio
async def test_ping_command():
    result = await dispatch({"command": "/ping", "text": ""})
    assert "pong" in result["text"]


@pytest.mark.asyncio
async def test_unknown_command():
    result = await dispatch({"command": "/nope", "text": ""})
    assert "Unknown command" in result["text"]


@pytest.mark.asyncio
async def test_klaxon_requires_text():
    result = await dispatch({"command": "/klaxon", "text": "  "})
    assert "Usage" in result["text"]


@pytest.mark.asyncio
async def test_conversation_session(tmp_db):
    from klaxon.agent.sessions import handle_user_message, reset_user_session
    from klaxon.db.engine import dispose_engine, reset_engine
    from klaxon.settings import reset_settings

    reset_settings()
    reset_engine()
    from klaxon.db.engine import init_db

    await init_db()

    reply1, conv1 = await handle_user_message(
        "hello",
        team_id="T1",
        channel_id="C1",
        user_id="U1",
    )
    assert "Echo" in reply1 or reply1
    reply2, conv2 = await handle_user_message(
        "follow up",
        team_id="T1",
        channel_id="C1",
        user_id="U1",
    )
    assert conv1 == conv2
    closed = await reset_user_session(team_id="T1", channel_id="C1", user_id="U1")
    assert closed >= 1
    _reply3, conv3 = await handle_user_message(
        "new session",
        team_id="T1",
        channel_id="C1",
        user_id="U1",
    )
    assert conv3 != conv1

    await dispose_engine()
    reset_engine()
    reset_settings()
