"""Conversation-aware agent entry used by Slack handlers."""

from __future__ import annotations

import logging

from klaxon.agent.service import run_agent
from klaxon.db.conversations import (
    add_message,
    end_conversation,
    get_messages,
    load_or_create_conversation,
    set_thread_ts,
)
from klaxon.db.engine import get_session_maker

log = logging.getLogger(__name__)


async def handle_user_message(
    text: str,
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str | None = None,
    force_new: bool = False,
) -> tuple[str, str]:
    """Run the agent with conversation memory.

    Returns (reply_text, conversation_id).
    """
    async with get_session_maker()() as session:
        conversation = await load_or_create_conversation(
            session,
            team_id=team_id,
            channel_id=channel_id,
            user_id=user_id,
            thread_ts=thread_ts,
            force_new=force_new,
        )
        conversation_id = conversation.id
        prior = await get_messages(session, conversation_id)
        history = [{"role": m.role, "content": m.content} for m in prior]
        await add_message(session, conversation_id, "user", text)

    reply = await run_agent(
        text,
        history=history,
        user_id=user_id,
        team_id=team_id,
    )

    async with get_session_maker()() as session:
        await add_message(session, conversation_id, "assistant", reply)
        if thread_ts:
            await set_thread_ts(session, conversation_id, thread_ts)

    return reply, conversation_id


async def reset_user_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
) -> int:
    async with get_session_maker()() as session:
        return await end_conversation(
            session,
            team_id=team_id,
            channel_id=channel_id,
            user_id=user_id,
        )
