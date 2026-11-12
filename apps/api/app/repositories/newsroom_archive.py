"""The archive: stories that went to air and the bulletin revisions that aired them.

"Went to air" means the story is pinned in a bulletin revision that was marked as broadcast. The archive keeps what
aired: a story rewritten afterwards still shows the version that was read, and unaired drafts are never searchable
or shown. Pure reads; everyone signed in to the newsroom can read the archive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    RadioBulletin,
    RadioBulletinItem,
    RadioBulletinRevision,
    Source,
    SourceItem,
    Story,
    StoryReview,
    StoryScript,
    User,
)
from app.repositories.incidents import _like
from app.repositories.newsroom_bulletins import revision_totals
from app.schemas.newsroom import NEWS_CATEGORY_LABELS
from app.schemas.newsroom_workflow import (
    ArchiveBulletin,
    ArchiveBulletinDetail,
    ArchiveBulletinItem,
    ArchiveBulletinRef,
    ArchiveReview,
    ArchiveScript,
    ArchiveStory,
    ArchiveStoryDetail,
    ArchiveStoryLink,
    ArchiveVersion,
    Person,
)

_CLASSIFICATION = SourceItem.source_metadata["classification"]
EXCERPT_CHARS = 240


@dataclass
class ArchiveFilters:
    q: str | None = None
    aired_from: datetime | None = None
    aired_to: datetime | None = None
    category: str | None = None


def _aired_items():
    """Every item of an aired revision: which story and script version went to air, in which bulletin, when."""
    return (
        select(
            RadioBulletinItem.story_id.label("story_id"),
            RadioBulletinItem.script_id.label("script_id"),
            RadioBulletinRevision.revision_number.label("revision_number"),
            RadioBulletinRevision.aired_at.label("aired_at"),
            RadioBulletinRevision.bulletin_id.label("bulletin_id"),
        )
        .join(RadioBulletinRevision, RadioBulletinRevision.id == RadioBulletinItem.revision_id)
        .where(RadioBulletinRevision.aired_at.is_not(None))
        .subquery("aired")
    )


def stories_query(f: ArchiveFilters) -> Select:
    """Stories that went to air, most recently first aired first."""
    aired = _aired_items()
    span = (
        select(
            aired.c.story_id,
            func.min(aired.c.aired_at).label("first_aired_at"),
            func.max(aired.c.aired_at).label("last_aired_at"),
        )
        .group_by(aired.c.story_id)
        .subquery("span")
    )
    query = (
        select(Story, span.c.first_aired_at, span.c.last_aired_at)
        .join(span, span.c.story_id == Story.id)
        .outerjoin(SourceItem, SourceItem.id == Story.source_item_id)
    )
    if f.q and f.q.strip():
        like = _like(f.q.strip())
        aired_text = (
            select(1)
            .select_from(aired)
            .join(StoryScript, StoryScript.id == aired.c.script_id)
            .where(aired.c.story_id == Story.id, or_(StoryScript.headline.ilike(like), StoryScript.body.ilike(like)))
            .exists()
        )
        query = query.where(or_(Story.title.ilike(like), aired_text))
    if f.aired_from or f.aired_to:
        window = [aired.c.story_id == Story.id]
        if f.aired_from:
            window.append(aired.c.aired_at >= f.aired_from)
        if f.aired_to:
            window.append(aired.c.aired_at <= f.aired_to)
        query = query.where(select(1).select_from(aired).where(*window).exists())
    if f.category:
        query = query.where(
            or_(
                _CLASSIFICATION["primary_category"].as_string() == f.category,
                _CLASSIFICATION["secondary_category"].as_string() == f.category,
            )
        )
    return query.order_by(span.c.first_aired_at.desc(), Story.id)


def _appearances(session: Session, story_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[tuple[uuid.UUID, ArchiveBulletinRef]]]:
    """Per story: (script id, where and when it aired), oldest first."""
    if not story_ids:
        return {}
    aired = _aired_items()
    out: dict[uuid.UUID, list[tuple[uuid.UUID, ArchiveBulletinRef]]] = {}
    for story_id, script_id, number, at, bulletin_id, name in session.execute(
        select(aired.c.story_id, aired.c.script_id, aired.c.revision_number, aired.c.aired_at, RadioBulletin.id, RadioBulletin.name)
        .join(RadioBulletin, RadioBulletin.id == aired.c.bulletin_id)
        .where(aired.c.story_id.in_(story_ids))
        .order_by(aired.c.aired_at, aired.c.revision_number)
    ):
        out.setdefault(story_id, []).append((script_id, ArchiveBulletinRef(id=bulletin_id, name=name, revision_number=number, aired_at=at)))
    return out


def _excerpt(body: str) -> str:
    flat = " ".join(body.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


def build_stories(session: Session, rows: list[Any]) -> list[ArchiveStory]:
    story_ids = [story.id for story, _, _ in rows]
    appearances = _appearances(session, story_ids)
    aired_script_ids = {sid for pairs in appearances.values() for sid, _ in pairs}
    scripts = {
        s.id: s for s in session.scalars(select(StoryScript).where(StoryScript.id.in_(aired_script_ids)))
    } if aired_script_ids else {}
    people = {u.id: u for u in session.scalars(select(User).where(User.id.in_({s.assignee_id for s, _, _ in rows})))} if rows else {}
    source_ids = [s.source_item_id for s, _, _ in rows if s.source_item_id]
    sources: dict[uuid.UUID, tuple[Any, str]] = {
        item.id: (item, name)
        for item, name in session.execute(
            select(SourceItem, Source.name).join(Source, Source.id == SourceItem.source_id).where(SourceItem.id.in_(source_ids))
        )
    } if source_ids else {}

    # One "aired" subquery per statement: each call to _aired_items() makes a new alias.
    aired = _aired_items()
    followed_ids = {s.follows_story_id for s, _, _ in rows if s.follows_story_id}
    followed = {f.id: f for f in session.scalars(select(Story).where(Story.id.in_(followed_ids)))} if followed_ids else {}
    first_aired = (
        dict(
            session.execute(
                select(aired.c.story_id, func.min(aired.c.aired_at)).where(aired.c.story_id.in_(followed_ids)).group_by(aired.c.story_id)
            ).all()
        )
        if followed_ids
        else {}
    )
    counting = _aired_items()
    follow_counts = (
        dict(
            session.execute(
                select(Story.follows_story_id, func.count())
                .where(Story.follows_story_id.in_(story_ids), Story.id.in_(select(counting.c.story_id)))
                .group_by(Story.follows_story_id)
            ).all()
        )
        if story_ids
        else {}
    )

    out: list[ArchiveStory] = []
    for story, first_at, last_at in rows:
        pairs = appearances.get(story.id, [])
        newest = max((scripts[sid] for sid, _ in pairs if sid in scripts), key=lambda s: s.version_number)
        source = sources.get(story.source_item_id) if story.source_item_id else None
        cls = ((source[0].source_metadata or {}).get("classification") or {}) if source else {}
        category = cls.get("primary_category")
        earlier = followed.get(story.follows_story_id) if story.follows_story_id else None
        out.append(
            ArchiveStory(
                id=story.id,
                title=story.title,
                headline=newest.headline,
                excerpt=_excerpt(newest.body),
                category=category,
                category_label=NEWS_CATEGORY_LABELS.get(category) if category else None,
                aired_at=first_at,
                last_aired_at=last_at,
                bulletins=_unique_bulletins(pairs),
                reporter=Person(id=story.assignee_id, display_name=people[story.assignee_id].display_name),
                follows=(
                    ArchiveStoryLink(id=earlier.id, title=earlier.title, aired_at=first_aired[earlier.id])
                    if earlier is not None and earlier.id in first_aired
                    else None
                ),
                follow_up_count=int(follow_counts.get(story.id, 0)),
                publisher=source[1] if source else None,
                source_url=(source[0].canonical_url or (source[0].source_metadata or {}).get("url")) if source else None,
            )
        )
    return out


def _unique_bulletins(pairs: list[tuple[uuid.UUID, ArchiveBulletinRef]]) -> list[ArchiveBulletinRef]:
    seen: set[tuple[uuid.UUID, int]] = set()
    out: list[ArchiveBulletinRef] = []
    for _, ref in pairs:
        key = (ref.id, ref.revision_number)
        if key not in seen:
            seen.add(key)
            out.append(ref)
    return out


def story_detail(session: Session, story_id: uuid.UUID) -> ArchiveStoryDetail | None:
    """One archived story: what aired, the whole version history, the decisions, and its follow-ups."""
    row = session.execute(stories_query(ArchiveFilters()).where(Story.id == story_id)).first()
    if row is None:  # never aired, so not in the archive
        return None
    (summary,) = build_stories(session, [row])

    appearances = _appearances(session, [story_id])[story_id]
    aired_by_script: dict[uuid.UUID, list[ArchiveBulletinRef]] = {}
    for script_id, ref in appearances:
        aired_by_script.setdefault(script_id, []).append(ref)

    story = session.get(Story, story_id)
    assert story is not None
    all_scripts = list(session.scalars(select(StoryScript).where(StoryScript.story_id == story_id).order_by(StoryScript.version_number)))
    reviews = list(session.scalars(select(StoryReview).where(StoryReview.story_id == story_id).order_by(StoryReview.reviewed_at, StoryReview.id)))
    version_of = {s.id: s.version_number for s in all_scripts}
    approved_ids = {r.script_id for r in reviews if r.decision == "approved"}
    user_ids = {s.created_by for s in all_scripts} | {r.reviewer_id for r in reviews}
    people = {u.id: Person(id=u.id, display_name=u.display_name) for u in session.scalars(select(User).where(User.id.in_(user_ids)))}

    aired = _aired_items()
    later = session.execute(
        select(Story, func.min(aired.c.aired_at))
        .join(aired, aired.c.story_id == Story.id)
        .where(Story.follows_story_id == story_id)
        .group_by(Story.id)
        .order_by(func.min(aired.c.aired_at))
    ).all()

    return ArchiveStoryDetail(
        **summary.model_dump(),
        source_item_id=story.source_item_id,
        scripts=[
            ArchiveScript(
                version_number=s.version_number, headline=s.headline, body=s.body, estimated_seconds=s.estimated_seconds,
                origin=s.origin, created_by=people[s.created_by], created_at=s.created_at, aired_in=aired_by_script[s.id],
            )
            for s in all_scripts
            if s.id in aired_by_script
        ],
        versions=[
            ArchiveVersion(
                version_number=s.version_number, origin=s.origin, created_by=people[s.created_by], created_at=s.created_at,
                approved=s.id in approved_ids, aired=s.id in aired_by_script,
            )
            for s in all_scripts
        ],
        reviews=[
            ArchiveReview(
                script_version=version_of[r.script_id], decision=r.decision, comment=r.comment, self_approved=r.self_approved,
                reviewer=people[r.reviewer_id], reviewed_at=r.reviewed_at,
            )
            for r in reviews
        ],
        followed_by=[ArchiveStoryLink(id=s.id, title=s.title, aired_at=at) for s, at in later],
    )


# ---- aired bulletin revisions -------------------------------------------------------------------------------------------


def bulletins_query(q: str | None, aired_from: datetime | None, aired_to: datetime | None) -> Select:
    """Bulletin revisions that went to air, newest first. A bulletin that aired twice (revision 1, then 2) shows both."""
    query = (
        select(RadioBulletinRevision, RadioBulletin)
        .join(RadioBulletin, RadioBulletin.id == RadioBulletinRevision.bulletin_id)
        .where(RadioBulletinRevision.aired_at.is_not(None))
    )
    if q and q.strip():
        like = _like(q.strip())
        story_match = (
            select(1)
            .select_from(RadioBulletinItem)
            .join(Story, Story.id == RadioBulletinItem.story_id)
            .where(RadioBulletinItem.revision_id == RadioBulletinRevision.id, Story.title.ilike(like))
            .exists()
        )
        query = query.where(or_(RadioBulletin.name.ilike(like), story_match))
    if aired_from:
        query = query.where(RadioBulletinRevision.aired_at >= aired_from)
    if aired_to:
        query = query.where(RadioBulletinRevision.aired_at <= aired_to)
    return query.order_by(RadioBulletinRevision.aired_at.desc(), RadioBulletinRevision.id)


def build_bulletins(session: Session, rows: list[Any]) -> list[ArchiveBulletin]:
    rev_ids = [r.id for r, _ in rows]
    totals = revision_totals(session, rev_ids)
    counts = dict(
        session.execute(
            select(RadioBulletinItem.revision_id, func.count()).where(RadioBulletinItem.revision_id.in_(rev_ids)).group_by(RadioBulletinItem.revision_id)
        ).all()
    ) if rev_ids else {}
    people = {u.id: Person(id=u.id, display_name=u.display_name) for u in session.scalars(select(User).where(User.id.in_({r.aired_by for r, _ in rows})))} if rows else {}
    return [
        ArchiveBulletin(
            id=b.id, name=b.name, scheduled_for=b.scheduled_for, revision_number=r.revision_number, aired_at=r.aired_at,
            aired_by=people[r.aired_by], total_seconds=totals.get(r.id, 0), story_count=int(counts.get(r.id, 0)),
        )
        for r, b in rows
    ]


def bulletin_detail(session: Session, bulletin_id: uuid.UUID, number: int) -> ArchiveBulletinDetail | None:
    """What exactly went to air in one aired revision, with the script text that was read."""
    row = session.execute(bulletins_query(None, None, None).where(RadioBulletin.id == bulletin_id, RadioBulletinRevision.revision_number == number)).first()
    if row is None:
        return None
    revision, _ = row
    (summary,) = build_bulletins(session, [row])
    items = session.execute(
        select(RadioBulletinItem, Story.title, StoryScript)
        .join(Story, Story.id == RadioBulletinItem.story_id)
        .join(StoryScript, StoryScript.id == RadioBulletinItem.script_id)
        .where(RadioBulletinItem.revision_id == revision.id)
        .order_by(RadioBulletinItem.position)
    ).all()
    bulletin = session.get(RadioBulletin, bulletin_id)
    assert bulletin is not None
    approver = session.get(User, revision.approved_by) if revision.approved_by else None
    return ArchiveBulletinDetail(
        **summary.model_dump(),
        target_seconds=bulletin.target_seconds,
        approved_at=revision.approved_at,
        approved_by=Person(id=approver.id, display_name=approver.display_name) if approver else None,
        items=[
            ArchiveBulletinItem(
                position=item.position, story_id=item.story_id, story_title=title, headline=script.headline, body=script.body,
                duration_seconds=item.duration_override_seconds or script.estimated_seconds,
                duration_overridden=item.duration_override_seconds is not None, note=item.note,
            )
            for item, title, script in items
        ],
    )
