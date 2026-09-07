"""Events API: mentions, DMs, and threaded follow-ups."""

from __future__ import annotations

import logging
import re
import time
from collections import OrderedDict
from typing import Any

from klaxon.agent.sessions import handle_user_message
from klaxon.db.engine import get_session_maker
from klaxon.db.models import Conversation
from klaxon.slack.client import SlackClient
from klaxon.slack.oauth import ensure_fresh_token
from klaxon.slack.store import InstallationStore

log = logging.getLogger(__name__)

_SEEN: OrderedDict[str, float] = OrderedDict()
_SEEN_TTL = 600
_SEEN_MAX = 5000


def already_processed(event_id: str) -> bool:
    now = time.time()
    while _SEEN and (
        now - next(iter(_SEEN.values())) > _SEEN_TTL or len(_SEEN) > _SEEN_MAX
    ):
        _SEEN.popitem(last=False)
    if event_id in _SEEN:
        return True
    _SEEN[event_id] = now
    return False


def strip_mention(text: str) -> str:
    return re.sub(r"<@[A-Z0-9]+>", "", text or "").strip()


async def handle_event(body: dict[str, Any], store: InstallationStore) -> None:
    event = body.get("event") or {}
    event_type = event.get("type")
    team_id = body.get("team_id") or (body.get("authorizations") or [{}])[0].get(
        "team_id"
    )

    if not team_id:
        log.warning("event without team_id: %s", event_type)
        return

    installation = await ensure_fresh_token(store, team_id)
    if installation is None:
        log.warning("event for uninstalled team %s", team_id)
        return

    if event.get("bot_id") or event.get("user") == installation.bot_user_id:
        return

    client = SlackClient(installation.bot_token)

    if event_type == "app_mention":
        await _on_mention(event, client, team_id)
    elif event_type == "message":
        if event.get("channel_type") == "im":
            await _on_dm(event, client, team_id)
        elif event.get("thread_ts") and not event.get("subtype"):
            await _on_thread_reply(event, client, team_id)
    elif event_type == "app_home_opened":
        await _on_home_opened(event, client)
    else:
        log.debug("unhandled event type: %s", event_type)


async def _on_mention(event: dict[str, Any], client: SlackClient, team_id: str) -> None:
    question = strip_mention(event.get("text", ""))
    if not question:
        return
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event["ts"]
    await client.add_reaction(channel, event["ts"], "eyes")
    placeholder = await client.post_message(channel, "_thinking..._", thread_ts=thread_ts)
    reply, _ = await handle_user_message(
        question,
        team_id=team_id,
        channel_id=channel,
        user_id=event.get("user", ""),
        thread_ts=thread_ts,
    )
    await client.update_message(channel, placeholder["ts"], reply)


async def _on_dm(event: dict[str, Any], client: SlackClient, team_id: str) -> None:
    if event.get("subtype"):
        return
    text = (event.get("text") or "").strip()
    if not text:
        return
    reply, _ = await handle_user_message(
        text,
        team_id=team_id,
        channel_id=event["channel"],
        user_id=event.get("user", ""),
    )
    await client.post_message(event["channel"], reply)


async def _on_thread_reply(
    event: dict[str, Any], client: SlackClient, team_id: str
) -> None:
    """Continue a conversation when the user replies in a Klaxon thread."""
    from sqlalchemy import select

    thread_ts = event.get("thread_ts")
    if not thread_ts:
        return
    text = (event.get("text") or "").strip()
    if not text:
        return

    async with get_session_maker()() as session:
        result = await session.execute(
            select(Conversation).where(
                Conversation.team_id == team_id,
                Conversation.channel_id == event["channel"],
                Conversation.thread_ts == thread_ts,
                Conversation.ended_at.is_(None),
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            return

    reply, _ = await handle_user_message(
        text,
        team_id=team_id,
        channel_id=event["channel"],
        user_id=event.get("user", ""),
        thread_ts=thread_ts,
    )
    await client.post_message(event["channel"], reply, thread_ts=thread_ts)


async def _on_home_opened(event: dict[str, Any], client: SlackClient) -> None:
    if event.get("tab") != "home":
        return
    await client.call(
        "views.publish",
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "Klaxon incident desk"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "Ask with `/klaxon …`, mention me, or DM me.\n"
                            "Use `/klaxon-reset` to start a fresh conversation."
                        ),
                    },
                },
            ],
        },
    )
