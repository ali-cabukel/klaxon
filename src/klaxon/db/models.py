"""SQLAlchemy models for incidents, conversations, and Slack installs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        Index("idx_issues_status", "status"),
        Index("idx_issues_kind", "kind"),
        Index("idx_issues_severity", "severity"),
        Index("idx_issues_public_id", "public_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="api")
    reporter: Mapped[str | None] = mapped_column(String(200))
    assignee: Mapped[str | None] = mapped_column(String(200))
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    labels: Mapped[list[IssueLabel]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    comments: Mapped[list[IssueComment]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    status_events: Mapped[list[StatusEvent]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )
    side_effects: Mapped[list[SideEffect]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )


class IssueLabel(Base):
    __tablename__ = "issue_labels"

    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True
    )
    label_name: Mapped[str] = mapped_column(String(100), primary_key=True)

    issue: Mapped[Issue] = relationship(back_populates="labels")


class IssueComment(Base):
    __tablename__ = "issue_comments"
    __table_args__ = (Index("idx_issue_comments_issue_id", "issue_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    author: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issue: Mapped[Issue] = relationship(back_populates="comments")


class StatusEvent(Base):
    __tablename__ = "status_events"
    __table_args__ = (Index("idx_status_events_issue_id", "issue_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(200), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issue: Mapped[Issue] = relationship(back_populates="status_events")


class SideEffect(Base):
    __tablename__ = "side_effects"
    __table_args__ = (Index("idx_side_effects_issue_id", "issue_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    issue_id: Mapped[int | None] = mapped_column(ForeignKey("issues.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="simulated")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    issue: Mapped[Issue | None] = relationship(back_populates="side_effects")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conversations_session", "team_id", "channel_id", "user_id"),
        Index("idx_conversations_thread", "thread_ts"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    team_id: Mapped[str] = mapped_column(String(32), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    thread_ts: Mapped[str | None] = mapped_column(String(32))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[ConversationMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (Index("idx_conversation_messages_conversation_id", "conversation_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Installation(Base):
    __tablename__ = "installations"

    team_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(200), nullable=False)
    bot_token_enc: Mapped[bytes] = mapped_column(nullable=False)
    bot_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    installer_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    refresh_token_enc: Mapped[bytes | None] = mapped_column()
    expires_at: Mapped[int | None] = mapped_column(Integer)
    enterprise_id: Mapped[str | None] = mapped_column(String(32))
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)
