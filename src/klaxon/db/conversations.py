"""Slack conversation session persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from klaxon.db.models import Conversation, ConversationMessage
from klaxon.settings import get_settings


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def load_or_create_conversation(
    session: AsyncSession,
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str | None = None,
    force_new: bool = False,
) -> Conversation:
    settings = get_settings()
    cutoff = _utcnow() - timedelta(seconds=settings.conversation_ttl_seconds)

    if not force_new:
        stmt = (
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(
                Conversation.team_id == team_id,
                Conversation.channel_id == channel_id,
                Conversation.user_id == user_id,
                Conversation.ended_at.is_(None),
                Conversation.updated_at >= cutoff,
            )
            .order_by(Conversation.updated_at.desc())
            .limit(1)
        )
        if thread_ts:
            stmt = (
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(
                    Conversation.team_id == team_id,
                    Conversation.channel_id == channel_id,
                    Conversation.thread_ts == thread_ts,
                    Conversation.ended_at.is_(None),
                )
                .order_by(Conversation.updated_at.desc())
                .limit(1)
            )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            if thread_ts and not existing.thread_ts:
                existing.thread_ts = thread_ts
                await session.commit()
            return existing

    conversation = Conversation(
        id=str(uuid.uuid4()),
        team_id=team_id,
        channel_id=channel_id,
        user_id=user_id,
        thread_ts=thread_ts,
    )
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


async def end_conversation(
    session: AsyncSession,
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
) -> int:
    result = await session.execute(
        select(Conversation).where(
            Conversation.team_id == team_id,
            Conversation.channel_id == channel_id,
            Conversation.user_id == user_id,
            Conversation.ended_at.is_(None),
        )
    )
    rows = list(result.scalars().all())
    now = _utcnow()
    for row in rows:
        row.ended_at = now
    await session.commit()
    return len(rows)


async def add_message(
    session: AsyncSession,
    conversation_id: str,
    role: str,
    content: str,
) -> ConversationMessage:
    message = ConversationMessage(
        conversation_id=conversation_id,
        role=role,
        content=content,
    )
    session.add(message)
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one()
    conversation.updated_at = _utcnow()
    await session.commit()
    await session.refresh(message)
    return message


async def get_messages(
    session: AsyncSession,
    conversation_id: str,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    return list(result.scalars().all())


async def set_thread_ts(
    session: AsyncSession,
    conversation_id: str,
    thread_ts: str,
) -> None:
    result = await session.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return
    conversation.thread_ts = thread_ts
    conversation.updated_at = _utcnow()
    await session.commit()
