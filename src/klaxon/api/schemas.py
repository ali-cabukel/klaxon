"""Pydantic schemas for the REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Kind = Literal["code", "data"]
Status = Literal["open", "acknowledged", "in_progress", "resolved", "closed"]
Severity = Literal["low", "medium", "high", "critical"]
Source = Literal["api", "slack", "upstream", "agent"]


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    kind: Kind = "code"
    status: Status = "open"
    severity: Severity = "medium"
    source: Source = "api"
    reporter: str | None = None
    assignee: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)


class IssueUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    severity: Severity | None = None
    assignee: str | None = None
    reporter: str | None = None
    features: dict[str, Any] | None = None
    labels: list[str] | None = None


class StatusUpdate(BaseModel):
    status: Status
    comment: str | None = None
    actor: str = "api"


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)
    author: str = "api"


class CommentOut(BaseModel):
    id: int
    author: str
    body: str
    created_at: str | None = None


class IssueOut(BaseModel):
    id: int
    public_id: str
    title: str
    description: str
    kind: str
    status: str
    severity: str
    source: str
    reporter: str | None = None
    assignee: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    resolved_at: str | None = None
    comments: list[CommentOut] | None = None


class IssueList(BaseModel):
    items: list[IssueOut]
    count: int
    limit: int
    offset: int


class StatsOut(BaseModel):
    group_by: str
    total: int
    counts: dict[str, int]


class IngestRequest(IssueCreate):
    source: Source = "upstream"
    create_github_issue: bool = False


class SideEffectOut(BaseModel):
    id: int
    issue_id: int | None = None
    action: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class SideEffectList(BaseModel):
    items: list[SideEffectOut]
    count: int
