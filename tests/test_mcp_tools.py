"""MCP / in-process tool tests."""

from __future__ import annotations

import json

import pytest

from klaxon.agent.tools import build_tools


@pytest.mark.asyncio
async def test_in_process_tools(tmp_db):
    from klaxon.db.engine import dispose_engine, reset_engine
    from klaxon.settings import reset_settings

    reset_settings()
    reset_engine()
    tools = {t.name: t for t in build_tools()}

    created = await tools["create_issue"].ainvoke(
        {
            "title": "Tool-created issue",
            "kind": "code",
            "severity": "low",
            "labels": "test",
        }
    )
    payload = json.loads(created)
    public_id = payload["public_id"]

    stats = await tools["issue_stats"].ainvoke({"group_by": "status"})
    assert json.loads(stats)["total"] >= 1

    fetched = await tools["get_issue"].ainvoke({"public_id": public_id})
    assert public_id in fetched

    effect = await tools["create_github_issue"].ainvoke({"public_id": public_id})
    assert "fake_url" in effect

    await dispose_engine()
    reset_engine()
    reset_settings()
