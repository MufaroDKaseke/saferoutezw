"""NUST FM radio bulletins API: ad hoc bulletins, numbered revisions and the approval of each revision.

Mounted only when ``APP_MODE=nust_newsroom``. Everyone signed in to the newsroom can read bulletins; building,
submitting, approving and broadcasting are the Executive Producer's (``APPROVER_ROLES`` in ``deps.py``).
Exactly one revision of a bulletin is approved at a time; changing an approved bulletin means a new revision,
and the approved one stays live until the new one is approved. Every change is audited with ids and state only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deps import Approver, DbSession, NewsroomReader
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.repositories import newsroom_bulletins as repo
from app.schemas.newsroom_workflow import (
    BulletinApproveRequest,
    BulletinCreate,
    BulletinDetail,
    BulletinItemsUpdate,
    BulletinRejectRequest,
    BulletinSummary,
    StudioView,
)
from app.services import newsroom_bulletins as flow

router = APIRouter(prefix="/newsroom", tags=["newsroom-bulletins"], responses=ERROR_RESPONSES)


def _detail(db: DbSession, bulletin_id: uuid.UUID) -> BulletinDetail:
    detail = repo.get_detail(db, bulletin_id)
    assert detail is not None
    return detail


@router.get("/bulletins", response_model=Page[BulletinSummary])
def list_bulletins(
    auth: NewsroomReader,
    db: DbSession,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200, description="Name contains")] = None,
    scheduled_from: datetime | None = None,
    scheduled_to: datetime | None = None,
    has_approved: Annotated[bool | None, Query(description="Only bulletins with (or without) an approved revision")] = None,
    aired: Annotated[bool | None, Query(description="Only bulletins that have (or have not) gone to air")] = None,
    order: Literal["asc", "desc"] = "desc",
) -> Page[BulletinSummary]:
    filters = repo.BulletinFilters(
        q=q, scheduled_from=scheduled_from, scheduled_to=scheduled_to, has_approved=has_approved, aired=aired,
        ascending=order == "asc",
    )
    rows, total = paginate(db, repo.bulletins_query(filters), pagination)
    return Page(
        items=repo.build_summaries(db, [b for (b,) in rows]), total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.get("/bulletins/{bulletin_id}/studio", response_model=StudioView)
def studio(bulletin_id: uuid.UUID, response: Response, auth: NewsroomReader, db: DbSession) -> StudioView:
    """The studio screen's authoritative check: the approved version to read, its script text, and whether a newer
    revision is waiting for approval. Open to every signed-in newsroom role (a reporter or the Executive Producer
    may be the one reading on air). Never cached: the screen polls this and must say so when it cannot get an answer.
    """
    view = repo.studio_view(db, bulletin_id)
    if view is None:
        raise not_found("BULLETIN_NOT_FOUND", "No such bulletin.")
    response.headers["Cache-Control"] = "no-store"
    return view


@router.post("/bulletins", response_model=BulletinDetail, status_code=201)
def create_bulletin(body: BulletinCreate, auth: Approver, db: DbSession) -> BulletinDetail:
    """Create a bulletin (name, air time, target length) with an empty first draft."""
    bulletin = flow.create_bulletin(
        db, auth.user, name=body.name, scheduled_for=body.scheduled_for, target_seconds=body.target_seconds
    )
    db.commit()
    return _detail(db, bulletin.id)


@router.get("/bulletins/{bulletin_id}", response_model=BulletinDetail)
def get_bulletin(bulletin_id: uuid.UUID, auth: NewsroomReader, db: DbSession) -> BulletinDetail:
    detail = repo.get_detail(db, bulletin_id)
    if detail is None:
        raise not_found("BULLETIN_NOT_FOUND", "No such bulletin.")
    return detail


@router.post("/bulletins/{bulletin_id}/revisions", response_model=BulletinDetail, status_code=201)
def create_revision(bulletin_id: uuid.UUID, auth: Approver, db: DbSession) -> BulletinDetail:
    """Start a new draft revision, copying the approved one. The approved revision stays live until this one is approved."""
    flow.new_revision(db, auth.user, bulletin_id)
    db.commit()
    return _detail(db, bulletin_id)


@router.put("/bulletins/{bulletin_id}/revisions/{number}/items", response_model=BulletinDetail)
def set_items(bulletin_id: uuid.UUID, number: int, body: BulletinItemsUpdate, auth: Approver, db: DbSession) -> BulletinDetail:
    """Replace the running order of a draft revision."""
    flow.replace_items(db, auth.user, bulletin_id, number, body.items)
    db.commit()
    return _detail(db, bulletin_id)


@router.post("/bulletins/{bulletin_id}/revisions/{number}/submit", response_model=BulletinDetail)
def submit_revision(bulletin_id: uuid.UUID, number: int, auth: Approver, db: DbSession) -> BulletinDetail:
    """Ask for approval. Refused unless every story's pinned script is approved."""
    flow.submit_revision(db, auth.user, bulletin_id, number)
    db.commit()
    return _detail(db, bulletin_id)


@router.post("/bulletins/{bulletin_id}/revisions/{number}/approve", response_model=BulletinDetail)
def approve_revision(
    bulletin_id: uuid.UUID, number: int, auth: Approver, db: DbSession, body: BulletinApproveRequest | None = None
) -> BulletinDetail:
    """Approve and make this revision the live one; the previous approved revision is superseded in the same transaction."""
    flow.approve_revision(db, auth.user, bulletin_id, number, body.comment if body else None)
    db.commit()
    return _detail(db, bulletin_id)


@router.post("/bulletins/{bulletin_id}/revisions/{number}/reject", response_model=BulletinDetail)
def reject_revision(
    bulletin_id: uuid.UUID, number: int, body: BulletinRejectRequest, auth: Approver, db: DbSession
) -> BulletinDetail:
    flow.reject_revision(db, auth.user, bulletin_id, number, body.comment)
    db.commit()
    return _detail(db, bulletin_id)


@router.post("/bulletins/{bulletin_id}/broadcast", response_model=BulletinDetail)
def broadcast_bulletin(bulletin_id: uuid.UUID, auth: Approver, db: DbSession) -> BulletinDetail:
    """Record that the approved revision went to air. Its stories become Broadcast and their articles Used."""
    flow.broadcast(db, auth.user, bulletin_id)
    db.commit()
    return _detail(db, bulletin_id)
