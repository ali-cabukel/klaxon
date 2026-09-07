"""REST API tests."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_healthz(client):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.asyncio
async def test_issue_crud_flow(client):
    create = await client.post(
        "/v1/issues",
        json={
            "title": "Broken pipeline",
            "kind": "data",
            "severity": "high",
            "description": "null keys",
            "labels": ["dq"],
            "features": {"table_name": "fact_orders"},
        },
    )
    assert create.status_code == 201
    body = create.json()
    public_id = body["public_id"]

    listed = await client.get("/v1/issues", params={"kind": "data"})
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    detail = await client.get(f"/v1/issues/{public_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Broken pipeline"

    status = await client.post(
        f"/v1/issues/{public_id}/status",
        json={"status": "acknowledged", "comment": "on it"},
    )
    assert status.status_code == 200
    assert status.json()["status"] == "acknowledged"

    comment = await client.post(
        f"/v1/issues/{public_id}/comments",
        json={"body": "checking upstream"},
    )
    assert comment.status_code == 201

    stats = await client.get("/v1/stats", params={"group_by": "severity"})
    assert stats.status_code == 200
    assert stats.json()["total"] >= 1


@pytest.mark.asyncio
async def test_ingest_with_github(client):
    resp = await client.post(
        "/v1/ingest",
        json={
            "title": "Upstream crash",
            "kind": "code",
            "severity": "critical",
            "create_github_issue": True,
            "features": {"repo": "acme/api"},
        },
    )
    assert resp.status_code == 201
    public_id = resp.json()["public_id"]
    assert resp.json()["source"] == "upstream"
    assert "github_issue_url" in resp.json()["features"]

    effects = await client.get("/v1/side-effects", params={"public_id": public_id})
    assert effects.status_code == 200
    assert effects.json()["count"] >= 1
