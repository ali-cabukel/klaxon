"""Issue CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from klaxon.api.deps import get_session
from klaxon.api.schemas import (
    CommentCreate,
    CommentOut,
    IssueCreate,
    IssueList,
    IssueOut,
    IssueUpdate,
    StatusUpdate,
)
from klaxon.db import repository as repo

router = APIRouter(prefix="/v1/issues", tags=["issues"])


@router.get("", response_model=IssueList)
async def list_issues(
    q: str | None = Query(None),
    kind: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> IssueList:
    issues = await repo.search_issues(
        session,
        query=q,
        kind=kind,
        status=status_filter,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    items = [IssueOut.model_validate(repo.issue_to_dict(i)) for i in issues]
    return IssueList(items=items, count=len(items), limit=limit, offset=offset)


@router.post("", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
async def create_issue(
    payload: IssueCreate,
    session: AsyncSession = Depends(get_session),
) -> IssueOut:
    try:
        issue = await repo.create_issue(session, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return IssueOut.model_validate(repo.issue_to_dict(issue))


@router.get("/{public_id}", response_model=IssueOut)
async def get_issue(
    public_id: str,
    session: AsyncSession = Depends(get_session),
) -> IssueOut:
    issue = await repo.get_issue(session, public_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue {public_id} not found")
    return IssueOut.model_validate(repo.issue_to_dict(issue, include_comments=True))


@router.patch("/{public_id}", response_model=IssueOut)
async def patch_issue(
    public_id: str,
    payload: IssueUpdate,
    session: AsyncSession = Depends(get_session),
) -> IssueOut:
    data = payload.model_dump(exclude_unset=True)
    try:
        issue = await repo.update_issue(session, public_id, **data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue {public_id} not found")
    return IssueOut.model_validate(repo.issue_to_dict(issue))


@router.post("/{public_id}/status", response_model=IssueOut)
async def change_status(
    public_id: str,
    payload: StatusUpdate,
    session: AsyncSession = Depends(get_session),
) -> IssueOut:
    try:
        issue = await repo.update_issue_status(
            session,
            public_id,
            payload.status,
            comment=payload.comment,
            actor=payload.actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue {public_id} not found")
    return IssueOut.model_validate(repo.issue_to_dict(issue))


@router.get("/{public_id}/comments", response_model=list[CommentOut])
async def get_comments(
    public_id: str,
    session: AsyncSession = Depends(get_session),
) -> list[CommentOut]:
    issue = await repo.get_issue(session, public_id)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"Issue {public_id} not found")
    comments = await repo.list_comments(session, public_id)
    return [CommentOut.model_validate(repo.comment_to_dict(c)) for c in comments]


@router.post(
    "/{public_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_comment(
    public_id: str,
    payload: CommentCreate,
    session: AsyncSession = Depends(get_session),
) -> CommentOut:
    comment = await repo.add_comment(
        session, public_id, payload.body, author=payload.author
    )
    if comment is None:
        raise HTTPException(status_code=404, detail=f"Issue {public_id} not found")
    return CommentOut.model_validate(repo.comment_to_dict(comment))
