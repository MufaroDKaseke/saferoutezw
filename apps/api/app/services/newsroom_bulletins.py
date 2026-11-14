"""NUST FM radio bulletins: numbered revisions, one approved at a time, and the atomic swap on approval.

A bulletin has revisions. Only a draft can be edited; submitting it asks the Executive Producer (approver
roles) to decide. Approving a revision runs in one transaction: the previously approved revision becomes
``superseded`` and the bulletin's ``approved_revision_id`` moves to the new one, so there is never a moment
with two approved revisions or none. Changing an approved bulletin means a new revision; the approved one stays
live (and is what the studio view shows) until the new one is approved. The database triggers enforce the same
rules, so they hold even if this code is bypassed. Every change writes an audit event (ids and state only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import APPROVER_ROLES
from app.api.errors import ApiError, conflict, forbidden, not_found
from app.models import (
    RadioBulletin,
    RadioBulletinDecision,
    RadioBulletinItem,
    RadioBulletinRevision,
    SourceItem,
    Story,
    StoryReview,
    StoryScript,
    User,
)
from app.models.enums import BulletinDecision, RevisionState, StoryStage
from app.schemas.newsroom_workflow import BulletinItemInput
from app.services.audit import record_audit

DRAFT = RevisionState.DRAFT.value
PENDING = RevisionState.PENDING_APPROVAL.value
APPROVED = RevisionState.APPROVED.value
OPEN_STATES = (DRAFT, PENDING)


def _require_approver(user: User) -> None:
    """Building, submitting, approving and airing a bulletin are the Executive Producer's (``APPROVER_ROLES``)."""
    if not user.is_active or user.role not in {r.value for r in APPROVER_ROLES}:
        raise forbidden("Only the Executive Producer can build, approve or broadcast a bulletin.")


def _lock_bulletin(session: Session, bulletin_id: uuid.UUID) -> RadioBulletin:
    bulletin = session.get(RadioBulletin, bulletin_id, with_for_update=True, populate_existing=True)
    if bulletin is None:
        raise not_found("BULLETIN_NOT_FOUND", "No such bulletin.")
    return bulletin


def _revision(session: Session, bulletin_id: uuid.UUID, number: int) -> RadioBulletinRevision:
    revision = session.scalar(
        select(RadioBulletinRevision).where(
            RadioBulletinRevision.bulletin_id == bulletin_id, RadioBulletinRevision.revision_number == number
        )
    )
    if revision is None:
        raise not_found("REVISION_NOT_FOUND", "No such revision.")
    return revision


def _items(session: Session, revision_id: uuid.UUID) -> list[RadioBulletinItem]:
    return list(
        session.scalars(
            select(RadioBulletinItem).where(RadioBulletinItem.revision_id == revision_id).order_by(RadioBulletinItem.position)
        )
    )


def approved_script_ids(session: Session, script_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """The scripts (of those given) that carry an approving review."""
    if not script_ids:
        return set()
    return set(
        session.scalars(
            select(StoryReview.script_id).where(StoryReview.decision == "approved", StoryReview.script_id.in_(script_ids))
        )
    )


# ---- operations -----------------------------------------------------------------------------------------------


def create_bulletin(session: Session, user: User, *, name: str, scheduled_for: datetime, target_seconds: int) -> RadioBulletin:
    """A new ad hoc bulletin with an empty first draft."""
    _require_approver(user)
    bulletin = RadioBulletin(name=name, scheduled_for=scheduled_for, target_seconds=target_seconds, created_by=user.id)
    session.add(bulletin)
    session.flush()
    revision = RadioBulletinRevision(bulletin_id=bulletin.id, revision_number=1, state=DRAFT, created_by=user.id)
    session.add(revision)
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_created", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"target_seconds": target_seconds, "scheduled_for": scheduled_for.isoformat(), "revision": 1},
    )
    return bulletin


def new_revision(session: Session, user: User, bulletin_id: uuid.UUID) -> RadioBulletinRevision:
    """Start a new draft revision, copying the approved one (or the newest, if none is approved yet)."""
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    open_revision = session.scalar(
        select(RadioBulletinRevision).where(
            RadioBulletinRevision.bulletin_id == bulletin.id, RadioBulletinRevision.state.in_(OPEN_STATES)
        )
    )
    if open_revision is not None:
        raise conflict(
            "REVISION_ALREADY_OPEN",
            f"Revision {open_revision.revision_number} is still {open_revision.state.replace('_', ' ')}. "
            "Finish or reject it before starting another.",
        )
    base = session.get(RadioBulletinRevision, bulletin.approved_revision_id) if bulletin.approved_revision_id else None
    if base is None:
        base = session.scalar(
            select(RadioBulletinRevision)
            .where(RadioBulletinRevision.bulletin_id == bulletin.id)
            .order_by(RadioBulletinRevision.revision_number.desc())
            .limit(1)
        )
    number = (session.scalar(select(func.max(RadioBulletinRevision.revision_number)).where(RadioBulletinRevision.bulletin_id == bulletin.id)) or 0) + 1
    revision = RadioBulletinRevision(bulletin_id=bulletin.id, revision_number=number, state=DRAFT, created_by=user.id)
    session.add(revision)
    session.flush()
    copied = _items(session, base.id) if base is not None else []
    for item in copied:
        session.add(
            RadioBulletinItem(
                revision_id=revision.id, position=item.position, story_id=item.story_id, script_id=item.script_id,
                duration_override_seconds=item.duration_override_seconds, note=item.note,
            )
        )
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_revision_created", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": number, "copied_from": base.revision_number if base else None, "items": len(copied)},
    )
    return revision


def _resolve_script(session: Session, story: Story, requested: uuid.UUID | None) -> StoryScript:
    if requested is not None:
        script = session.get(StoryScript, requested)
        if script is None or script.story_id != story.id:
            raise ApiError(422, "SCRIPT_NOT_FOUND", f"That script is not a version of “{story.title}”.")
        return script
    scripts = list(session.scalars(select(StoryScript).where(StoryScript.story_id == story.id).order_by(StoryScript.version_number.desc())))
    if not scripts:
        raise ApiError(422, "STORY_HAS_NO_SCRIPT", f"“{story.title}” has no script yet.")
    approved = approved_script_ids(session, [s.id for s in scripts])
    return next((s for s in scripts if s.id in approved), scripts[0])  # the approved version, else the newest


def replace_items(
    session: Session, user: User, bulletin_id: uuid.UUID, number: int, items: list[BulletinItemInput]
) -> RadioBulletinRevision:
    """Set the running order of a draft revision. Each story is pinned to one exact script version."""
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    revision = _revision(session, bulletin.id, number)
    if revision.state != DRAFT:
        raise conflict("REVISION_LOCKED", "Only a draft revision can be edited. Start a new revision to change this bulletin.")
    story_ids = [i.story_id for i in items]
    if len(set(story_ids)) != len(story_ids):
        raise ApiError(422, "DUPLICATE_STORY", "A story can only appear once in a bulletin.")
    stories = {s.id: s for s in session.scalars(select(Story).where(Story.id.in_(story_ids)))} if story_ids else {}
    rows: list[RadioBulletinItem] = []
    for position, entry in enumerate(items, start=1):
        story = stories.get(entry.story_id)
        if story is None:
            raise not_found("STORY_NOT_FOUND", "One of those stories does not exist.")
        if story.stage == StoryStage.DROPPED.value:
            raise ApiError(422, "STORY_DROPPED", f"“{story.title}” was dropped and cannot go in a bulletin.")
        script = _resolve_script(session, story, entry.script_id)
        rows.append(
            RadioBulletinItem(
                revision_id=revision.id, position=position, story_id=story.id, script_id=script.id,
                duration_override_seconds=entry.duration_override_seconds, note=entry.note or None,
            )
        )
    # Executed straight away (not through the unit of work, which would insert before it deletes).
    session.execute(delete(RadioBulletinItem).where(RadioBulletinItem.revision_id == revision.id))
    session.add_all(rows)
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_items_saved", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": number, "items": len(rows)},
    )
    return revision


def submit_revision(session: Session, user: User, bulletin_id: uuid.UUID, number: int) -> RadioBulletinRevision:
    """Ask the Executive Producer to approve. Every item's pinned script must already be approved."""
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    revision = _revision(session, bulletin.id, number)
    if revision.state != DRAFT:
        raise conflict("INVALID_STATE", f"A revision that is {revision.state.replace('_', ' ')} cannot be submitted.")
    items = _items(session, revision.id)
    if not items:
        raise conflict("EMPTY_BULLETIN", "Add at least one story before submitting the bulletin.")
    approved = approved_script_ids(session, [i.script_id for i in items])
    stories = {s.id: s for s in session.scalars(select(Story).where(Story.id.in_([i.story_id for i in items])))}
    problems: list[dict[str, str]] = []
    for item in items:
        story = stories[item.story_id]
        if story.stage == StoryStage.DROPPED.value:
            problems.append({"field": f"items.{item.position}", "message": f"“{story.title}” was dropped."})
        elif item.script_id not in approved:
            problems.append({"field": f"items.{item.position}", "message": f"The script for “{story.title}” has not been approved."})
    if problems:
        raise ApiError(
            409, "SCRIPT_NOT_APPROVED",
            "Every story in the bulletin needs an approved script before it can be submitted.", details=problems,
        )
    revision.state = PENDING
    revision.submitted_by = user.id
    revision.submitted_at = datetime.now(UTC)
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_submitted", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": number, "items": len(items)},
    )
    return revision


def approve_revision(
    session: Session, user: User, bulletin_id: uuid.UUID, number: int, comment: str | None
) -> RadioBulletinRevision:
    """Approve a submitted revision and make it the live one, atomically.

    The old approved revision becomes ``superseded`` and ``approved_revision_id`` moves to this one in the same
    transaction. The Executive Producer may approve a bulletin they submitted: allowed, but flagged.
    """
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    revision = _revision(session, bulletin.id, number)
    if revision.state != PENDING:
        raise conflict("INVALID_STATE", "Only a submitted revision can be approved.")
    self_approved = user.id == revision.submitted_by
    session.add(
        RadioBulletinDecision(
            revision_id=revision.id, reviewer_id=user.id, decision=BulletinDecision.APPROVED.value,
            comment=(comment or "").strip() or None, self_approved=self_approved,
        )
    )
    session.flush()  # the database guards below look for this decision

    superseded = None
    if bulletin.approved_revision_id is not None:
        old = session.get(RadioBulletinRevision, bulletin.approved_revision_id, with_for_update=True, populate_existing=True)
        if old is not None and old.id != revision.id:
            old.state = RevisionState.SUPERSEDED.value
            superseded = old.revision_number
            session.flush()  # at most one approved revision exists at any moment
    revision.state = APPROVED
    revision.approved_by = user.id
    revision.approved_at = datetime.now(UTC)
    session.flush()
    bulletin.approved_revision_id = revision.id
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_approved", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": number, "superseded_revision": superseded, "self_approved": self_approved},
    )
    return revision


def reject_revision(
    session: Session, user: User, bulletin_id: uuid.UUID, number: int, comment: str
) -> RadioBulletinRevision:
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    revision = _revision(session, bulletin.id, number)
    if revision.state != PENDING:
        raise conflict("INVALID_STATE", "Only a submitted revision can be rejected.")
    comment = comment.strip()
    if not comment:
        raise ApiError(422, "COMMENT_REQUIRED", "Say what needs to change when rejecting a bulletin.")
    session.add(
        RadioBulletinDecision(
            revision_id=revision.id, reviewer_id=user.id, decision=BulletinDecision.REJECTED.value, comment=comment
        )
    )
    session.flush()
    revision.state = RevisionState.REJECTED.value
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_rejected", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": number},
    )
    return revision


def _mark_article_used(session: Session, item: SourceItem, user: User, bulletin_id: uuid.UUID) -> None:
    """A story that went to air sets its article to Used (the newsroom's article flag)."""
    previous = (item.source_metadata or {}).get("newsroom_review", {}).get("status", "new")
    if previous == "used":
        return
    item.source_metadata = {
        **(item.source_metadata or {}),
        "newsroom_review": {
            "status": "used",
            "by": user.display_name,
            "by_id": str(user.id),
            "at": datetime.now(UTC).isoformat(),
            "note": "Broadcast",
        },
    }
    record_audit(
        session, actor_id=user.id, action="newsroom.article_reviewed", entity_type="source_item", entity_id=item.id,
        details={"status": "used", "previous": previous, "via": "broadcast", "bulletin_id": str(bulletin_id)},
    )


def broadcast(session: Session, user: User, bulletin_id: uuid.UUID) -> RadioBulletinRevision:
    """Record that the approved revision went to air. Its stories become ``broadcast`` and their articles Used."""
    _require_approver(user)
    bulletin = _lock_bulletin(session, bulletin_id)
    if bulletin.approved_revision_id is None:
        raise conflict("NOT_APPROVED", "There is no approved revision to broadcast.")
    revision = session.get(RadioBulletinRevision, bulletin.approved_revision_id, with_for_update=True, populate_existing=True)
    assert revision is not None
    if revision.aired_at is not None:
        raise conflict("ALREADY_AIRED", "This revision has already been marked as broadcast. Changes need a new revision.")
    revision.aired_by = user.id
    revision.aired_at = datetime.now(UTC)
    session.flush()

    aired_stories = 0
    for item in _items(session, revision.id):
        story = session.get(Story, item.story_id, with_for_update=True, populate_existing=True)
        if story is None:
            continue
        # A story that has been reopened with a newer script stays as it is; the archive keeps what aired.
        if story.stage == StoryStage.APPROVED.value:
            story.stage = StoryStage.BROADCAST.value
            session.flush()
            aired_stories += 1
        if story.source_item_id is not None:
            article = session.get(SourceItem, story.source_item_id)
            if article is not None:
                _mark_article_used(session, article, user, bulletin.id)
    record_audit(
        session, actor_id=user.id, action="newsroom.bulletin_aired", entity_type="radio_bulletin", entity_id=bulletin.id,
        details={"revision": revision.revision_number, "stories_marked_broadcast": aired_stories},
    )
    return revision

