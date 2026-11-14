"""Radio bulletin queries: bulletins and their revisions as the builder and the studio view show them.

Pure reads. Durations: an item's duration is its override (a clip) or the pinned script's reading-time
estimate; a revision's total is the sum of its items'.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import (
    RadioBulletin,
    RadioBulletinDecision,
    RadioBulletinItem,
    RadioBulletinRevision,
    Story,
    StoryReview,
    StoryScript,
    User,
)
from app.repositories.incidents import _like
from app.schemas.newsroom_workflow import (
    BulletinDecisionOut,
    BulletinDetail,
    BulletinItemOut,
    BulletinSummary,
    Person,
    RevisionOut,
    ScriptRef,
    StoryRef,
    StudioItem,
    StudioView,
    WorkflowSummary,
)

APPROVED = "approved"


@dataclass
class BulletinFilters:
    q: str | None = None
    scheduled_from: datetime | None = None
    scheduled_to: datetime | None = None
    has_approved: bool | None = None
    aired: bool | None = None
    ascending: bool = False


def bulletins_query(f: BulletinFilters) -> Select:
    query = select(RadioBulletin)
    if f.q and f.q.strip():
        query = query.where(RadioBulletin.name.ilike(_like(f.q.strip())))
    if f.scheduled_from:
        query = query.where(RadioBulletin.scheduled_for >= f.scheduled_from)
    if f.scheduled_to:
        query = query.where(RadioBulletin.scheduled_for <= f.scheduled_to)
    if f.has_approved is True:
        query = query.where(RadioBulletin.approved_revision_id.is_not(None))
    elif f.has_approved is False:
        query = query.where(RadioBulletin.approved_revision_id.is_(None))
    if f.aired is not None:
        aired = (
            select(RadioBulletinRevision.id)
            .where(RadioBulletinRevision.bulletin_id == RadioBulletin.id, RadioBulletinRevision.aired_at.is_not(None))
            .exists()
        )
        query = query.where(aired if f.aired else ~aired)
    order = RadioBulletin.scheduled_for.asc() if f.ascending else RadioBulletin.scheduled_for.desc()
    return query.order_by(order, RadioBulletin.id)


def _people(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Person]:
    if not ids:
        return {}
    return {
        u.id: Person(id=u.id, display_name=u.display_name) for u in session.scalars(select(User).where(User.id.in_(ids)))
    }


def revision_totals(session: Session, revision_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not revision_ids:
        return {}
    rows = session.execute(
        select(
            RadioBulletinItem.revision_id,
            func.sum(func.coalesce(RadioBulletinItem.duration_override_seconds, StoryScript.estimated_seconds)),
        )
        .join(StoryScript, StoryScript.id == RadioBulletinItem.script_id)
        .where(RadioBulletinItem.revision_id.in_(revision_ids))
        .group_by(RadioBulletinItem.revision_id)
    ).all()
    return {rid: int(total) for rid, total in rows}


def build_summaries(session: Session, bulletins: list[RadioBulletin]) -> list[BulletinSummary]:
    if not bulletins:
        return []
    revisions = list(
        session.scalars(
            select(RadioBulletinRevision)
            .where(RadioBulletinRevision.bulletin_id.in_([b.id for b in bulletins]))
            .order_by(RadioBulletinRevision.bulletin_id, RadioBulletinRevision.revision_number)
        )
    )
    by_bulletin: dict[uuid.UUID, list[RadioBulletinRevision]] = {}
    for r in revisions:
        by_bulletin.setdefault(r.bulletin_id, []).append(r)
    totals = revision_totals(session, [r.id for r in revisions if r.state == APPROVED])
    people = _people(session, {b.created_by for b in bulletins})
    out = []
    for b in bulletins:
        revs = by_bulletin.get(b.id, [])
        approved = next((r for r in revs if r.id == b.approved_revision_id), None)
        latest = revs[-1]
        out.append(
            BulletinSummary(
                id=b.id,
                name=b.name,
                scheduled_for=b.scheduled_for,
                target_seconds=b.target_seconds,
                approved_revision_number=approved.revision_number if approved else None,
                approved_at=approved.approved_at if approved else None,
                approved_total_seconds=totals.get(approved.id, 0) if approved else None,
                latest_revision_number=latest.revision_number,
                latest_revision_state=latest.state,
                aired_at=next((r.aired_at for r in revs if r.aired_at is not None), None),
                created_by=people[b.created_by],
                created_at=b.created_at,
            )
        )
    return out


def build_revisions(session: Session, bulletin_id: uuid.UUID) -> list[RevisionOut]:
    revisions = list(
        session.scalars(
            select(RadioBulletinRevision)
            .where(RadioBulletinRevision.bulletin_id == bulletin_id)
            .order_by(RadioBulletinRevision.revision_number)
        )
    )
    rev_ids = [r.id for r in revisions]
    rows = session.execute(
        select(RadioBulletinItem, Story, StoryScript)
        .join(Story, Story.id == RadioBulletinItem.story_id)
        .join(StoryScript, StoryScript.id == RadioBulletinItem.script_id)
        .where(RadioBulletinItem.revision_id.in_(rev_ids))
        .order_by(RadioBulletinItem.revision_id, RadioBulletinItem.position)
    ).all()
    story_ids = {story.id for _, story, _ in rows}
    script_ids = {script.id for _, _, script in rows}
    approved_scripts = (
        set(
            session.scalars(
                select(StoryReview.script_id).where(StoryReview.decision == APPROVED, StoryReview.script_id.in_(script_ids))
            )
        )
        if script_ids
        else set()
    )
    latest_version = (
        dict(
            session.execute(
                select(StoryScript.story_id, func.max(StoryScript.version_number))
                .where(StoryScript.story_id.in_(story_ids))
                .group_by(StoryScript.story_id)
            ).all()
        )
        if story_ids
        else {}
    )
    decisions = list(
        session.scalars(
            select(RadioBulletinDecision)
            .where(RadioBulletinDecision.revision_id.in_(rev_ids))
            .order_by(RadioBulletinDecision.decided_at, RadioBulletinDecision.id)
        )
    )
    people = _people(
        session,
        {
            uid
            for r in revisions
            for uid in (r.created_by, r.submitted_by, r.approved_by, r.aired_by)
            if uid is not None
        }
        | {d.reviewer_id for d in decisions},
    )

    items_by_rev: dict[uuid.UUID, list[BulletinItemOut]] = {}
    for item, story, script in rows:
        newest = latest_version.get(story.id, script.version_number)
        items_by_rev.setdefault(item.revision_id, []).append(
            BulletinItemOut(
                position=item.position,
                story=StoryRef(id=story.id, title=story.title, stage=story.stage),
                script=ScriptRef(
                    id=script.id,
                    version_number=script.version_number,
                    headline=script.headline,
                    estimated_seconds=script.estimated_seconds,
                ),
                script_approved=script.id in approved_scripts,
                newer_script_version=newest if newest > script.version_number else None,
                duration_seconds=item.duration_override_seconds or script.estimated_seconds,
                duration_overridden=item.duration_override_seconds is not None,
                note=item.note,
            )
        )
    decisions_by_rev: dict[uuid.UUID, list[BulletinDecisionOut]] = {}
    for d in decisions:
        decisions_by_rev.setdefault(d.revision_id, []).append(
            BulletinDecisionOut(
                decision=d.decision,
                comment=d.comment,
                self_approved=d.self_approved,
                reviewer=people[d.reviewer_id],
                decided_at=d.decided_at,
            )
        )

    person = lambda uid: people[uid] if uid is not None else None  # noqa: E731
    out: list[RevisionOut] = []
    for r in revisions:
        items = items_by_rev.get(r.id, [])
        out.append(
            RevisionOut(
                id=r.id,
                revision_number=r.revision_number,
                state=r.state,
                items=items,
                total_seconds=sum(i.duration_seconds for i in items),
                created_by=people[r.created_by],
                created_at=r.created_at,
                submitted_by=person(r.submitted_by),
                submitted_at=r.submitted_at,
                approved_by=person(r.approved_by),
                approved_at=r.approved_at,
                aired_by=person(r.aired_by),
                aired_at=r.aired_at,
                decisions=decisions_by_rev.get(r.id, []),
            )
        )
    return out


def get_detail(session: Session, bulletin_id: uuid.UUID) -> BulletinDetail | None:
    bulletin = session.get(RadioBulletin, bulletin_id)
    if bulletin is None:
        return None
    (summary,) = build_summaries(session, [bulletin])
    return BulletinDetail(**summary.model_dump(), revisions=build_revisions(session, bulletin_id))


NEXT_BULLETIN_GRACE = timedelta(hours=2)


def next_bulletin_summary(session: Session, now: datetime) -> BulletinSummary | None:
    """The soonest bulletin that has not gone to air yet. One that is a little late still counts as next."""
    aired = (
        select(RadioBulletinRevision.id)
        .where(RadioBulletinRevision.bulletin_id == RadioBulletin.id, RadioBulletinRevision.aired_at.is_not(None))
        .exists()
    )
    bulletin: Any = session.scalar(
        select(RadioBulletin)
        .where(RadioBulletin.scheduled_for >= now - NEXT_BULLETIN_GRACE, ~aired)
        .order_by(RadioBulletin.scheduled_for, RadioBulletin.id)
        .limit(1)
    )
    return build_summaries(session, [bulletin])[0] if bulletin else None


def workflow_summary(session: Session, now: datetime) -> WorkflowSummary:
    """The dashboard's story-to-air counters."""
    count = lambda *where: session.scalar(select(func.count()).select_from(Story).where(*where)) or 0  # noqa: E731
    closed = ("broadcast", "dropped")
    return WorkflowSummary(
        stories_awaiting_approval=count(Story.stage == "in_review"),
        stories_in_progress=count(Story.stage.not_in(closed)),
        bulletins_awaiting_approval=session.scalar(
            select(func.count()).select_from(RadioBulletinRevision).where(RadioBulletinRevision.state == "pending_approval")
        )
        or 0,
        next_bulletin=next_bulletin_summary(session, now),
    )


def studio_view(session: Session, bulletin_id: uuid.UUID) -> StudioView | None:
    """The studio screen's one answer: the approved revision's running order with the script text, and whether a
    newer revision is waiting. Deliberately small: no history, decisions or other revisions."""
    bulletin = session.get(RadioBulletin, bulletin_id)
    if bulletin is None:
        return None
    approved = (
        session.get(RadioBulletinRevision, bulletin.approved_revision_id) if bulletin.approved_revision_id is not None else None
    )
    items: list[StudioItem] = []
    if approved is not None:
        rows = session.execute(
            select(RadioBulletinItem, Story.title, StoryScript)
            .join(Story, Story.id == RadioBulletinItem.story_id)
            .join(StoryScript, StoryScript.id == RadioBulletinItem.script_id)
            .where(RadioBulletinItem.revision_id == approved.id)
            .order_by(RadioBulletinItem.position)
        ).all()
        items = [
            StudioItem(
                position=item.position,
                story_title=title,
                headline=script.headline,
                body=script.body,
                duration_seconds=item.duration_override_seconds or script.estimated_seconds,
                duration_overridden=item.duration_override_seconds is not None,
                note=item.note,
            )
            for item, title, script in rows
        ]
    # "Pending" means submitted and waiting for the Executive Producer; a draft still being edited is not shown.
    pending = session.scalar(
        select(RadioBulletinRevision.revision_number)
        .where(
            RadioBulletinRevision.bulletin_id == bulletin.id,
            RadioBulletinRevision.state == "pending_approval",
        )
        .limit(1)
    )
    approved_by = session.get(User, approved.approved_by) if approved is not None and approved.approved_by else None
    return StudioView(
        bulletin_id=bulletin.id,
        name=bulletin.name,
        scheduled_for=bulletin.scheduled_for,
        target_seconds=bulletin.target_seconds,
        status="approved" if approved is not None else "not_approved",
        version=approved.revision_number if approved is not None else None,
        approved_at=approved.approved_at if approved is not None else None,
        approved_by=Person(id=approved_by.id, display_name=approved_by.display_name) if approved_by else None,
        items=items,
        total_seconds=sum(i.duration_seconds for i in items),
        newer_revision_pending=pending is not None,
        newer_revision_number=pending,
        aired_at=approved.aired_at if approved is not None else None,
        server_time=datetime.now(UTC),
    )
