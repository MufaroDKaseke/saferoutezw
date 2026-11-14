"""Story-to-air queries: stories as the board and the workspace show them.

Pure reads. A story's "latest script" is its highest version number; its "approved script" is the highest
version that carries an approving review (an approval is only ever recorded against the newest script, so
that is also the most recently approved one).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session

from app.api.deps import STORY_WRITE_ROLES
from app.core.config import Settings
from app.models import Source, SourceItem, Story, StoryReview, StoryScript, User
from app.models.enums import CLOSED_STORY_STAGES, UserRole
from app.repositories.incidents import _like
from app.schemas.newsroom_workflow import (
    ArticleLink,
    Assignee,
    Person,
    ScriptOut,
    StoryDetail,
    StoryLink,
    StoryReviewOut,
    StorySummary,
    Verification,
)

CLOSED = tuple(s.value for s in CLOSED_STORY_STAGES)


@dataclass
class StoryFilters:
    stages: list[str] = field(default_factory=list)
    assignee_id: uuid.UUID | None = None
    q: str | None = None
    source_item_id: uuid.UUID | None = None


def stories_query(f: StoryFilters, viewer: User) -> Select:
    """Newest activity first. Reporters only ever get their own stories."""
    query = (
        select(Story, User, SourceItem.title_redacted)
        .join(User, User.id == Story.assignee_id)
        .outerjoin(SourceItem, SourceItem.id == Story.source_item_id)
    )
    if viewer.role == UserRole.REPORTER.value:
        query = query.where(Story.assignee_id == viewer.id)
    if f.stages:
        query = query.where(Story.stage.in_(f.stages))
    if f.assignee_id:
        query = query.where(Story.assignee_id == f.assignee_id)
    if f.source_item_id:
        query = query.where(Story.source_item_id == f.source_item_id)
    if f.q and f.q.strip():
        query = query.where(Story.title.ilike(_like(f.q.strip())))
    return query.order_by(Story.updated_at.desc(), Story.id)


def _script_facts(session: Session, story_ids: list[uuid.UUID]) -> tuple[dict, dict]:
    """(latest script per story as (version, seconds), approved script version per story)."""
    if not story_ids:
        return {}, {}
    newest = (
        select(StoryScript.story_id.label("story_id"), func.max(StoryScript.version_number).label("version"))
        .where(StoryScript.story_id.in_(story_ids))
        .group_by(StoryScript.story_id)
        .subquery()
    )
    latest = {
        sid: (version, seconds)
        for sid, version, seconds in session.execute(
            select(StoryScript.story_id, StoryScript.version_number, StoryScript.estimated_seconds).join(
                newest, and_(newest.c.story_id == StoryScript.story_id, newest.c.version == StoryScript.version_number)
            )
        )
    }
    approved = dict(
        session.execute(
            select(StoryScript.story_id, func.max(StoryScript.version_number))
            .join(StoryReview, StoryReview.script_id == StoryScript.id)
            .where(StoryReview.decision == "approved", StoryScript.story_id.in_(story_ids))
            .group_by(StoryScript.story_id)
        ).all()
    )
    return latest, approved


def _summary_fields(story: Story, assignee: User, headline: str | None, latest: dict, approved: dict) -> dict[str, Any]:
    version, seconds = latest.get(story.id, (None, None))
    return dict(
        id=story.id,
        title=story.title,
        stage=story.stage,
        assignee=Person(id=assignee.id, display_name=assignee.display_name),
        deadline_at=story.deadline_at,
        source_item_id=story.source_item_id,
        article_headline=headline,
        verified=story.verified_at is not None,
        latest_script_version=version,
        latest_script_seconds=seconds,
        approved_script_version=approved.get(story.id),
        follows_story_id=story.follows_story_id,
        created_at=story.created_at,
        updated_at=story.updated_at,
    )


def build_summaries(session: Session, rows: list[Any]) -> list[StorySummary]:
    latest, approved = _script_facts(session, [story.id for story, _, _ in rows])
    return [StorySummary(**_summary_fields(story, user, headline, latest, approved)) for story, user, headline in rows]


def get_detail(session: Session, story_id: uuid.UUID, settings: Settings) -> StoryDetail | None:
    row = session.execute(
        select(Story, User, SourceItem.title_redacted)
        .join(User, User.id == Story.assignee_id)
        .outerjoin(SourceItem, SourceItem.id == Story.source_item_id)
        .where(Story.id == story_id)
    ).first()
    if row is None:
        return None
    story, assignee, headline = row
    latest, approved = _script_facts(session, [story.id])

    scripts = list(
        session.scalars(select(StoryScript).where(StoryScript.story_id == story.id).order_by(StoryScript.version_number))
    )
    reviews = list(
        session.scalars(select(StoryReview).where(StoryReview.story_id == story.id).order_by(StoryReview.reviewed_at, StoryReview.id))
    )
    user_ids = {assignee.id, *(s.created_by for s in scripts), *(r.reviewer_id for r in reviews)}
    if story.verified_by:
        user_ids.add(story.verified_by)
    people = {u.id: u for u in session.scalars(select(User).where(User.id.in_(user_ids)))}
    person = lambda uid: Person(id=uid, display_name=people[uid].display_name)  # noqa: E731
    versions = {s.id: s.version_number for s in scripts}

    verification = None
    if story.verified_at is not None and story.verified_by is not None and story.verification_note is not None:
        verification = Verification(note=story.verification_note, at=story.verified_at, by=person(story.verified_by))

    article = None
    if story.source_item_id is not None:
        found = session.execute(
            select(SourceItem, Source.name)
            .join(Source, Source.id == SourceItem.source_id)
            .where(SourceItem.id == story.source_item_id)
        ).first()
        if found is not None:
            item, publisher = found
            article = ArticleLink(
                id=item.id,
                headline=item.title_redacted,
                publisher=publisher,
                source_url=item.canonical_url or (item.source_metadata or {}).get("url"),
                published_at=item.published_at,
            )

    return StoryDetail(
        **_summary_fields(story, assignee, headline, latest, approved),
        verification=verification,
        article=article,
        scripts=[
            ScriptOut(
                id=s.id, version_number=s.version_number, headline=s.headline, body=s.body,
                estimated_seconds=s.estimated_seconds, origin=s.origin, model_name=s.model_name,
                prompt_version=s.prompt_version, created_by=person(s.created_by), created_at=s.created_at,
            )
            for s in scripts
        ],
        reviews=[
            StoryReviewOut(
                id=r.id, script_id=r.script_id, script_version=versions[r.script_id], decision=r.decision,
                comment=r.comment, self_approved=r.self_approved, reviewer=person(r.reviewer_id),
                reviewed_at=r.reviewed_at,
            )
            for r in reviews
        ],
        reading_wpm=settings.newsroom_reading_wpm,
    )


def story_link_for_article(session: Session, article_id: uuid.UUID) -> StoryLink | None:
    """The story built from an article: the open one if there is one, otherwise the most recent."""
    row = session.execute(
        select(Story, User)
        .join(User, User.id == Story.assignee_id)
        .where(Story.source_item_id == article_id)
        .order_by(case((Story.stage.in_(CLOSED), 1), else_=0), Story.created_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    story, assignee = row
    return StoryLink(
        id=story.id, title=story.title, stage=story.stage,
        assignee=Person(id=assignee.id, display_name=assignee.display_name),
    )


def assignable_people(session: Session) -> list[Assignee]:
    """Active people a story can be assigned to (reporters and the Executive Producer)."""
    roles = [r.value for r in STORY_WRITE_ROLES]
    users = session.scalars(
        select(User).where(User.is_active.is_(True), User.role.in_(roles)).order_by(User.display_name, User.id)
    )
    return [Assignee(id=u.id, display_name=u.display_name, role=u.role) for u in users]
