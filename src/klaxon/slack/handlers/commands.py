"""Slash command handling for /klaxon, /klaxon-reset, /ping."""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any, Awaitable, Callable

from klaxon.agent.sessions import handle_user_message, reset_user_session
from klaxon.db.conversations import set_thread_ts
from klaxon.db.engine import get_session_maker
from klaxon.slack.client import SlackClient, respond_via_url
from klaxon.slack.oauth import ensure_fresh_token
from klaxon.slack.store import get_installation_store

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, str]], Awaitable[dict[str, Any] | None]]
_REGISTRY: dict[str, Handler] = {}


def command(name: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _REGISTRY[name] = fn
        return fn

    return decorator


async def dispatch(payload: dict[str, str]) -> dict[str, Any] | None:
    handler = _REGISTRY.get(payload.get("command", ""))
    if handler is None:
        return {
            "response_type": "ephemeral",
            "text": f"Unknown command `{payload.get('command')}`.",
        }
    return await handler(payload)


@command("/ping")
async def _ping(payload: dict[str, str]) -> dict[str, Any]:
    return {"response_type": "ephemeral", "text": "pong"}


@command("/klaxon")
async def _klaxon(payload: dict[str, str]) -> dict[str, Any]:
    question = (payload.get("text") or "").strip()
    if not question:
        return {
            "response_type": "ephemeral",
            "text": (
                "Usage: `/klaxon how many open critical issues?`\n"
                "Follow up with another `/klaxon …` or reply in the thread."
            ),
        }
    asyncio.create_task(_answer_later(payload, question))
    return {"response_type": "ephemeral", "text": f"_Working on:_ {question}"}


@command("/klaxon-reset")
async def _klaxon_reset(payload: dict[str, str]) -> dict[str, Any]:
    count = await reset_user_session(
        team_id=payload.get("team_id", ""),
        channel_id=payload.get("channel_id", ""),
        user_id=payload.get("user_id", ""),
    )
    return {
        "response_type": "ephemeral",
        "text": f"Conversation reset ({count} session(s) closed).",
    }


async def _answer_later(payload: dict[str, str], question: str) -> None:
    try:
        reply, conversation_id = await handle_user_message(
            question,
            team_id=payload.get("team_id", ""),
            channel_id=payload.get("channel_id", ""),
            user_id=payload.get("user_id", ""),
        )

        # Prefer chat.postMessage so we can bind thread_ts for follow-ups.
        posted = False
        installation = await ensure_fresh_token(
            get_installation_store(), payload.get("team_id", "")
        )
        if installation is not None:
            client = SlackClient(installation.bot_token)
            result = await client.post_message(
                payload["channel_id"],
                reply,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Q:* {question}"},
                    },
                    {"type": "section", "text": {"type": "mrkdwn", "text": reply}},
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"asked by <@{payload['user_id']}> · "
                                    "reply in this thread to continue"
                                ),
                            }
                        ],
                    },
                ],
            )
            thread_ts = result.get("ts")
            if thread_ts:
                async with get_session_maker()() as session:
                    await set_thread_ts(session, conversation_id, thread_ts)
            posted = True

        if not posted:
            await respond_via_url(
                payload["response_url"],
                {
                    "response_type": "in_channel",
                    "text": reply,
                    "blocks": [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*Q:* {question}"},
                        },
                        {"type": "section", "text": {"type": "mrkdwn", "text": reply}},
                    ],
                },
            )
    except Exception:
        log.exception("background /klaxon failed")
        await respond_via_url(
            payload["response_url"],
            {"response_type": "ephemeral", "text": "Something went wrong. Try again."},
        )


def parse_args(text: str) -> list[str]:
    return shlex.split(text or "")
