"""Stats, ingest, and side-effect routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from klaxon.api.deps import get_session
from klaxon.api.schemas import (
    IngestRequest,
    IssueOut,
    SideEffectList,
    SideEffectOut,
    StatsOut,
)
from klaxon.db import repository as repo

router = APIRouter(prefix="/v1", tags=["ops"])


@router.get("/stats", response_model=StatsOut)
async def stats(
    group_by: str = Query("status", pattern="^(status|kind|severity|source)$"),
    since: datetime | None = None,
    until: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> StatsOut:
    try:
        result = await repo.issue_stats(
            session, group_by=group_by, since=since, until=until
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StatsOut.model_validate(result)


@router.post("/ingest", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
async def ingest(
    payload: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> IssueOut:
    data = payload.model_dump(exclude={"create_github_issue"})
    data["source"] = data.get("source") or "upstream"
    try:
        issue = await repo.create_issue(session, **data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if payload.create_github_issue:
        await repo.simulate_github_issue(session, issue.public_id)
        refreshed = await repo.get_issue(session, issue.public_id)
        if refreshed is not None:
            issue = refreshed
    return IssueOut.model_validate(repo.issue_to_dict(issue))


@router.get("/side-effects", response_model=SideEffectList)
async def side_effects(
    public_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> SideEffectList:
    effects = await repo.list_side_effects(session, public_id=public_id, limit=limit)
    items = [SideEffectOut.model_validate(repo.side_effect_to_dict(e)) for e in effects]
    return SideEffectList(items=items, count=len(items))
