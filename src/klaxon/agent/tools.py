"""In-process LangChain tools mirroring the MCP surface (fallback / tests)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from klaxon.db.engine import get_session_maker, init_db
from klaxon.db import repository as repo


def _dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def build_tools():
    @tool
    async def search_issues(
        query: str = "",
        kind: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 20,
    ) -> str:
        """Search incident issues by text, kind, status, or severity."""
        await init_db()
        async with get_session_maker()() as session:
            issues = await repo.search_issues(
                session,
                query=query or None,
                kind=kind,
                status=status,
                severity=severity,
                limit=min(limit, 50),
            )
            if not issues:
                return "No issues matched."
            return _dumps([repo.issue_to_dict(i) for i in issues])

    @tool
    async def get_issue(public_id: str) -> str:
        """Get full details for an issue by public_id (e.g. INC-0001)."""
        await init_db()
        async with get_session_maker()() as session:
            issue = await repo.get_issue(session, public_id)
            if issue is None:
                return f"Issue {public_id} not found."
            return _dumps(repo.issue_to_dict(issue, include_comments=True))

    @tool
    async def issue_stats(
        group_by: str = "status",
        since: str | None = None,
        until: str | None = None,
    ) -> str:
        """Aggregate issue counts by status, kind, severity, or source."""
        await init_db()
        since_dt = datetime.fromisoformat(since) if since else None
        until_dt = datetime.fromisoformat(until) if until else None
        async with get_session_maker()() as session:
            try:
                result = await repo.issue_stats(
                    session, group_by=group_by, since=since_dt, until=until_dt
                )
            except ValueError as exc:
                return str(exc)
            return _dumps(result)

    @tool
    async def create_issue(
        title: str,
        description: str = "",
        kind: str = "code",
        severity: str = "medium",
        status: str = "open",
        source: str = "agent",
        reporter: str | None = None,
        assignee: str | None = None,
        labels: str = "",
        features_json: str = "{}",
    ) -> str:
        """Create a new incident issue."""
        await init_db()
        label_list = [s.strip() for s in labels.split(",") if s.strip()]
        try:
            features = json.loads(features_json) if features_json else {}
        except json.JSONDecodeError:
            return "features_json must be valid JSON."
        async with get_session_maker()() as session:
            try:
                issue = await repo.create_issue(
                    session,
                    title=title,
                    description=description,
                    kind=kind,
                    severity=severity,
                    status=status,
                    source=source,
                    reporter=reporter,
                    assignee=assignee,
                    labels=label_list,
                    features=features,
                )
            except ValueError as exc:
                return str(exc)
            return _dumps(repo.issue_to_dict(issue))

    @tool
    async def update_issue(
        public_id: str,
        title: str | None = None,
        description: str | None = None,
        severity: str | None = None,
        assignee: str | None = None,
        reporter: str | None = None,
        labels: str | None = None,
        features_json: str | None = None,
    ) -> str:
        """Update fields on an existing issue."""
        await init_db()
        kwargs: dict[str, Any] = {}
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if severity is not None:
            kwargs["severity"] = severity
        if assignee is not None:
            kwargs["assignee"] = assignee
        if reporter is not None:
            kwargs["reporter"] = reporter
        if labels is not None:
            kwargs["labels"] = [s.strip() for s in labels.split(",") if s.strip()]
        if features_json is not None:
            try:
                kwargs["features"] = json.loads(features_json)
            except json.JSONDecodeError:
                return "features_json must be valid JSON."
        async with get_session_maker()() as session:
            try:
                issue = await repo.update_issue(session, public_id, **kwargs)
            except ValueError as exc:
                return str(exc)
            if issue is None:
                return f"Issue {public_id} not found."
            return _dumps(repo.issue_to_dict(issue))

    @tool
    async def update_issue_status(
        public_id: str,
        status: str,
        comment: str | None = None,
        actor: str = "agent",
    ) -> str:
        """Change an issue's status and optionally add a comment."""
        await init_db()
        async with get_session_maker()() as session:
            try:
                issue = await repo.update_issue_status(
                    session, public_id, status, comment=comment, actor=actor
                )
            except ValueError as exc:
                return str(exc)
            if issue is None:
                return f"Issue {public_id} not found."
            return _dumps(repo.issue_to_dict(issue))

    @tool
    async def add_comment(public_id: str, body: str, author: str = "agent") -> str:
        """Add a comment to an issue."""
        await init_db()
        async with get_session_maker()() as session:
            comment = await repo.add_comment(session, public_id, body, author=author)
            if comment is None:
                return f"Issue {public_id} not found."
            return _dumps(repo.comment_to_dict(comment))

    @tool
    async def simulate_upstream_ingest(
        title: str,
        description: str = "",
        kind: str = "code",
        severity: str = "medium",
        features_json: str = "{}",
        create_github_issue: bool = False,
    ) -> str:
        """Simulate an upstream system creating an issue."""
        await init_db()
        try:
            features = json.loads(features_json) if features_json else {}
        except json.JSONDecodeError:
            return "features_json must be valid JSON."
        async with get_session_maker()() as session:
            try:
                issue = await repo.create_issue(
                    session,
                    title=title,
                    description=description,
                    kind=kind,
                    severity=severity,
                    source="upstream",
                    features=features,
                )
            except ValueError as exc:
                return str(exc)
            if create_github_issue:
                await repo.simulate_github_issue(session, issue.public_id)
                issue = await repo.get_issue(session, issue.public_id)  # type: ignore[assignment]
            return _dumps(repo.issue_to_dict(issue))

    @tool
    async def create_github_issue(
        public_id: str,
        title: str | None = None,
        body: str | None = None,
    ) -> str:
        """Simulate opening a GitHub issue (side effect only)."""
        await init_db()
        async with get_session_maker()() as session:
            effect = await repo.simulate_github_issue(
                session, public_id, title=title, body=body
            )
            if effect is None:
                return f"Issue {public_id} not found."
            return _dumps(repo.side_effect_to_dict(effect))

    @tool
    async def list_side_effects(public_id: str | None = None, limit: int = 20) -> str:
        """List simulated side effects."""
        await init_db()
        async with get_session_maker()() as session:
            effects = await repo.list_side_effects(
                session, public_id=public_id, limit=min(limit, 50)
            )
            if not effects:
                return "No side effects found."
            return _dumps([repo.side_effect_to_dict(e) for e in effects])

    return [
        search_issues,
        get_issue,
        issue_stats,
        create_issue,
        update_issue,
        update_issue_status,
        add_comment,
        simulate_upstream_ingest,
        create_github_issue,
        list_side_effects,
    ]
