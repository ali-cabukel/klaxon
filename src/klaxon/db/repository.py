"""Incident repository — single data path for REST and MCP."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from klaxon.db.models import Issue, IssueComment, IssueLabel, SideEffect, StatusEvent

VALID_KINDS = frozenset({"code", "data"})
VALID_STATUSES = frozenset({"open", "acknowledged", "in_progress", "resolved", "closed"})
VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
VALID_SOURCES = frozenset({"api", "slack", "upstream", "agent"})
TERMINAL_STATUSES = frozenset({"resolved", "closed"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def issue_to_dict(issue: Issue, *, include_comments: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": issue.id,
        "public_id": issue.public_id,
        "title": issue.title,
        "description": issue.description,
        "kind": issue.kind,
        "status": issue.status,
        "severity": issue.severity,
        "source": issue.source,
        "reporter": issue.reporter,
        "assignee": issue.assignee,
        "features": issue.features or {},
        "labels": [label.label_name for label in issue.labels],
        "created_at": issue.created_at.isoformat() if issue.created_at else None,
        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None,
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
    }
    if include_comments:
        payload["comments"] = [
            {
                "id": c.id,
                "author": c.author,
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in issue.comments
        ]
    return payload


def side_effect_to_dict(effect: SideEffect) -> dict[str, Any]:
    return {
        "id": effect.id,
        "issue_id": effect.issue_id,
        "action": effect.action,
        "status": effect.status,
        "payload": effect.payload or {},
        "created_at": effect.created_at.isoformat() if effect.created_at else None,
    }


def comment_to_dict(comment: IssueComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "issue_id": comment.issue_id,
        "author": comment.author,
        "body": comment.body,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


async def _next_public_id(session: AsyncSession) -> str:
    result = await session.execute(select(func.count()).select_from(Issue))
    count = int(result.scalar_one())
    return f"INC-{count + 1:04d}"


def _issue_query() -> Select[tuple[Issue]]:
    return select(Issue).options(
        selectinload(Issue.labels),
        selectinload(Issue.comments),
        selectinload(Issue.side_effects),
    )


async def create_issue(
    session: AsyncSession,
    *,
    title: str,
    description: str = "",
    kind: str = "code",
    status: str = "open",
    severity: str = "medium",
    source: str = "api",
    reporter: str | None = None,
    assignee: str | None = None,
    features: dict[str, Any] | None = None,
    labels: list[str] | None = None,
) -> Issue:
    if kind not in VALID_KINDS:
        raise ValueError(f"Invalid kind: {kind}")
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid source: {source}")

    public_id = await _next_public_id(session)
    issue = Issue(
        public_id=public_id,
        title=title,
        description=description or "",
        kind=kind,
        status=status,
        severity=severity,
        source=source,
        reporter=reporter,
        assignee=assignee,
        features=features or {},
        resolved_at=_utcnow() if status in TERMINAL_STATUSES else None,
    )
    session.add(issue)
    await session.flush()

    for name in labels or []:
        session.add(IssueLabel(issue_id=issue.id, label_name=name.strip()))

    session.add(
        StatusEvent(
            issue_id=issue.id,
            from_status=None,
            to_status=status,
            comment="created",
            actor=reporter or source,
        )
    )
    await session.commit()
    return await get_issue(session, public_id)  # type: ignore[return-value]


async def get_issue(session: AsyncSession, public_id: str) -> Issue | None:
    result = await session.execute(
        _issue_query().where(Issue.public_id == public_id)
    )
    return result.scalar_one_or_none()


async def search_issues(
    session: AsyncSession,
    *,
    query: str | None = None,
    kind: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Issue]:
    stmt = _issue_query()
    if query:
        pattern = f"%{query}%"
        stmt = stmt.where(
            or_(
                Issue.title.ilike(pattern),
                Issue.description.ilike(pattern),
                Issue.public_id.ilike(pattern),
                Issue.assignee.ilike(pattern),
                Issue.reporter.ilike(pattern),
            )
        )
    if kind:
        stmt = stmt.where(Issue.kind == kind)
    if status:
        stmt = stmt.where(Issue.status == status)
    if severity:
        stmt = stmt.where(Issue.severity == severity)
    stmt = stmt.order_by(Issue.created_at.desc()).limit(min(limit, 200)).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_issue(
    session: AsyncSession,
    public_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    severity: str | None = None,
    assignee: str | None = None,
    reporter: str | None = None,
    features: dict[str, Any] | None = None,
    labels: list[str] | None = None,
) -> Issue | None:
    issue = await get_issue(session, public_id)
    if issue is None:
        return None
    if title is not None:
        issue.title = title
    if description is not None:
        issue.description = description
    if severity is not None:
        if severity not in VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")
        issue.severity = severity
    if assignee is not None:
        issue.assignee = assignee
    if reporter is not None:
        issue.reporter = reporter
    if features is not None:
        merged = dict(issue.features or {})
        merged.update(features)
        issue.features = merged
    if labels is not None:
        issue.labels.clear()
        await session.flush()
        for name in labels:
            session.add(IssueLabel(issue_id=issue.id, label_name=name.strip()))
    issue.updated_at = _utcnow()
    await session.commit()
    return await get_issue(session, public_id)


async def update_issue_status(
    session: AsyncSession,
    public_id: str,
    status: str,
    *,
    comment: str | None = None,
    actor: str = "system",
) -> Issue | None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    issue = await get_issue(session, public_id)
    if issue is None:
        return None
    from_status = issue.status
    issue.status = status
    issue.updated_at = _utcnow()
    if status in TERMINAL_STATUSES:
        issue.resolved_at = _utcnow()
    elif from_status in TERMINAL_STATUSES:
        issue.resolved_at = None
    session.add(
        StatusEvent(
            issue_id=issue.id,
            from_status=from_status,
            to_status=status,
            comment=comment,
            actor=actor,
        )
    )
    if comment:
        session.add(
            IssueComment(issue_id=issue.id, author=actor, body=comment)
        )
    await session.commit()
    return await get_issue(session, public_id)


async def add_comment(
    session: AsyncSession,
    public_id: str,
    body: str,
    *,
    author: str = "system",
) -> IssueComment | None:
    issue = await get_issue(session, public_id)
    if issue is None:
        return None
    comment = IssueComment(issue_id=issue.id, author=author, body=body)
    session.add(comment)
    issue.updated_at = _utcnow()
    await session.commit()
    await session.refresh(comment)
    return comment


async def list_comments(session: AsyncSession, public_id: str) -> list[IssueComment]:
    issue = await get_issue(session, public_id)
    if issue is None:
        return []
    return list(issue.comments)


async def issue_stats(
    session: AsyncSession,
    *,
    group_by: str = "status",
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    if group_by not in {"status", "kind", "severity", "source"}:
        raise ValueError(f"Invalid group_by: {group_by}")
    column = getattr(Issue, group_by)
    stmt = select(column, func.count()).select_from(Issue)
    if since is not None:
        stmt = stmt.where(Issue.created_at >= since)
    if until is not None:
        stmt = stmt.where(Issue.created_at <= until)
    stmt = stmt.group_by(column)
    result = await session.execute(stmt)
    counts = {str(key): int(value) for key, value in result.all()}
    total = sum(counts.values())
    return {"group_by": group_by, "total": total, "counts": counts}


async def create_side_effect(
    session: AsyncSession,
    *,
    action: str,
    payload: dict[str, Any] | None = None,
    issue_id: int | None = None,
    status: str = "simulated",
) -> SideEffect:
    effect = SideEffect(
        issue_id=issue_id,
        action=action,
        status=status,
        payload=payload or {},
    )
    session.add(effect)
    await session.commit()
    await session.refresh(effect)
    return effect


async def list_side_effects(
    session: AsyncSession,
    *,
    public_id: str | None = None,
    limit: int = 50,
) -> list[SideEffect]:
    stmt = select(SideEffect).order_by(SideEffect.created_at.desc()).limit(min(limit, 200))
    if public_id:
        issue = await get_issue(session, public_id)
        if issue is None:
            return []
        stmt = stmt.where(SideEffect.issue_id == issue.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def simulate_github_issue(
    session: AsyncSession,
    public_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
) -> SideEffect | None:
    issue = await get_issue(session, public_id)
    if issue is None:
        return None
    gh_number = issue.id
    fake_url = f"https://github.com/simulated/klaxon/issues/{gh_number}"
    payload = {
        "title": title or issue.title,
        "body": body or issue.description,
        "fake_url": fake_url,
        "number": gh_number,
    }
    effect = await create_side_effect(
        session,
        action="create_github_issue",
        payload=payload,
        issue_id=issue.id,
    )
    features = dict(issue.features or {})
    features["github_issue_url"] = fake_url
    features["github_issue_number"] = gh_number
    issue.features = features
    issue.updated_at = _utcnow()
    await session.commit()
    await session.refresh(effect)
    return effect
