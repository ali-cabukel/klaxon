"""Repository and seed tests."""

from __future__ import annotations

import pytest

from klaxon.db import repository as repo
from klaxon.seed import SEED_ISSUES, seed


@pytest.mark.asyncio
async def test_create_and_get_issue(db_session):
    issue = await repo.create_issue(
        db_session,
        title="Test failure",
        description="boom",
        kind="code",
        severity="high",
        labels=["backend"],
        features={"repo": "acme/app"},
    )
    assert issue.public_id.startswith("INC-")
    fetched = await repo.get_issue(db_session, issue.public_id)
    assert fetched is not None
    assert fetched.title == "Test failure"
    assert [label.label_name for label in fetched.labels] == ["backend"]


@pytest.mark.asyncio
async def test_search_and_stats(db_session):
    await repo.create_issue(
        db_session, title="Null in orders", kind="data", severity="critical"
    )
    await repo.create_issue(
        db_session, title="API timeout", kind="code", severity="medium"
    )
    found = await repo.search_issues(db_session, query="orders", kind="data")
    assert len(found) == 1
    stats = await repo.issue_stats(db_session, group_by="kind")
    assert stats["total"] == 2
    assert stats["counts"]["data"] == 1


@pytest.mark.asyncio
async def test_status_and_github_side_effect(db_session):
    issue = await repo.create_issue(db_session, title="Crash", kind="code")
    updated = await repo.update_issue_status(
        db_session, issue.public_id, "in_progress", comment="looking"
    )
    assert updated is not None
    assert updated.status == "in_progress"
    effect = await repo.simulate_github_issue(db_session, issue.public_id)
    assert effect is not None
    assert effect.action == "create_github_issue"
    assert "fake_url" in effect.payload
    refreshed = await repo.get_issue(db_session, issue.public_id)
    assert refreshed is not None
    assert "github_issue_url" in (refreshed.features or {})


@pytest.mark.asyncio
async def test_seed(tmp_db):
    from klaxon.db.engine import dispose_engine, get_session_maker, reset_engine
    from klaxon.settings import reset_settings

    reset_settings()
    reset_engine()
    count = await seed()
    assert count == len(SEED_ISSUES)
    async with get_session_maker()() as session:
        issues = await repo.search_issues(session, limit=100)
        assert len(issues) == len(SEED_ISSUES)
    assert await seed() == 0  # skip when already seeded
    await dispose_engine()
    reset_engine()
    reset_settings()
