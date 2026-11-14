"""NUST FM story-to-air API: stories, their script versions and the approval decision.

Mounted only when ``APP_MODE=nust_newsroom``. Reporters act on their own stories; the Executive Producer
(``editor``) and admins act on all of them; analysts read. Only approver roles (``APPROVER_ROLES`` in
``deps.py``) may approve or send a story back. Every change is audited with ids and state only.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import AppSettings, Approver, DbSession, NewsroomReader, StoryWriter
from app.api.errors import ERROR_RESPONSES, not_found
from app.api.pagination import Page, Pagination, paginate
from app.models import Story
from app.repositories import newsroom_workflow as repo
from app.schemas.newsroom_workflow import (
    Assignee,
    DraftRequest,
    ScriptCreate,
    StoryCreate,
    StoryDecisionRequest,
    StoryDetail,
    StoryStageName,
    StorySummary,
    StoryUpdate,
    VerifyRequest,
)
from app.services import newsroom_workflow as flow
from app.services.newsroom_script import DEFAULT_TARGET_SECONDS, ScriptDrafter, drafter_from_settings

router = APIRouter(prefix="/newsroom", tags=["newsroom-stories"], responses=ERROR_RESPONSES)


def get_script_drafter(settings: AppSettings) -> ScriptDrafter:
    """The AI script drafter. Tests override this dependency with a fake, so nothing calls OpenAI."""
    return drafter_from_settings(settings)


Drafter = Annotated[ScriptDrafter, Depends(get_script_drafter)]


def _detail(db: DbSession, settings: AppSettings, story_id: uuid.UUID) -> StoryDetail:
    detail = repo.get_detail(db, story_id, settings)
    assert detail is not None
    return detail


@router.get("/assignees", response_model=list[Assignee])
def list_assignees(auth: Approver, db: DbSession) -> list[Assignee]:
    """People a story can be assigned to: the picker for the Executive Producer."""
    return repo.assignable_people(db)


@router.post("/stories", response_model=StoryDetail, status_code=201)
def create_story(body: StoryCreate, auth: StoryWriter, db: DbSession, settings: AppSettings) -> StoryDetail:
    """Take an article (or start an original story). Reporters take stories for themselves."""
    story = flow.create_story(
        db,
        auth.user,
        title=body.title,
        source_item_id=body.source_item_id,
        assignee_id=body.assignee_id,
        deadline_at=body.deadline_at,
        follows_story_id=body.follows_story_id,
    )
    db.commit()
    return _detail(db, settings, story.id)


@router.get("/stories", response_model=Page[StorySummary])
def list_stories(
    auth: NewsroomReader,
    db: DbSession,
    pagination: Pagination,
    stage: Annotated[list[StoryStageName] | None, Query(description="One or more stages; repeat to combine")] = None,
    assignee_id: uuid.UUID | None = None,
    source_item_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Title contains")] = None,
) -> Page[StorySummary]:
    filters = repo.StoryFilters(stages=list(stage or []), assignee_id=assignee_id, q=q, source_item_id=source_item_id)
    rows, total = paginate(db, repo.stories_query(filters, auth.user), pagination)
    return Page(
        items=repo.build_summaries(db, rows), total=total, page=pagination.page, page_size=pagination.page_size
    )


@router.get("/stories/{story_id}", response_model=StoryDetail)
def get_story(story_id: uuid.UUID, auth: NewsroomReader, db: DbSession, settings: AppSettings) -> StoryDetail:
    story = db.get(Story, story_id)
    if story is None:
        raise not_found("STORY_NOT_FOUND", "No such story.")
    flow.require_view(auth.user, story)
    return _detail(db, settings, story_id)


@router.patch("/stories/{story_id}", response_model=StoryDetail)
def update_story(
    story_id: uuid.UUID, body: StoryUpdate, auth: StoryWriter, db: DbSession, settings: AppSettings
) -> StoryDetail:
    flow.update_story(db, auth.user, story_id, body.model_dump(exclude_unset=True))
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/verify", response_model=StoryDetail)
def verify_story(
    story_id: uuid.UUID, body: VerifyRequest, auth: StoryWriter, db: DbSession, settings: AppSettings
) -> StoryDetail:
    """Record how the facts were checked. Needed before submitting."""
    flow.record_verification(db, auth.user, story_id, body.note)
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/scripts", response_model=StoryDetail, status_code=201)
def save_script(
    story_id: uuid.UUID, body: ScriptCreate, auth: StoryWriter, db: DbSession, settings: AppSettings
) -> StoryDetail:
    """Save a new script version. Editing an approved story's script reopens it as a draft."""
    flow.save_script(
        db, settings, auth.user, story_id, headline=body.headline, body=body.body, base_version=body.base_version
    )
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/scripts/draft", response_model=StoryDetail, status_code=201)
def draft_script(
    story_id: uuid.UUID,
    body: DraftRequest,
    auth: StoryWriter,
    db: DbSession,
    settings: AppSettings,
    drafter: Drafter,
) -> StoryDetail:
    """Ask the AI for a first draft, on request only. The story must be verified and come from an article.

    The draft is saved as an "AI draft" version for the reporter to edit; it never approves anything.
    Answers 503 when no OpenAI key is configured.
    """
    flow.draft_script(
        db,
        settings,
        auth.user,
        story_id,
        drafter,
        base_version=body.base_version,
        target_seconds=body.target_seconds or DEFAULT_TARGET_SECONDS,
    )
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/submit", response_model=StoryDetail)
def submit_story(story_id: uuid.UUID, auth: StoryWriter, db: DbSession, settings: AppSettings) -> StoryDetail:
    flow.submit_story(db, auth.user, story_id)
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/review", response_model=StoryDetail)
def review_story(
    story_id: uuid.UUID, body: StoryDecisionRequest, auth: Approver, db: DbSession, settings: AppSettings
) -> StoryDetail:
    """Approve the submitted script or send it back with a comment."""
    flow.review_story(
        db, auth.user, story_id, decision=body.decision, script_version=body.script_version, comment=body.comment
    )
    db.commit()
    return _detail(db, settings, story_id)


@router.post("/stories/{story_id}/drop", response_model=StoryDetail)
def drop_story(story_id: uuid.UUID, auth: StoryWriter, db: DbSession, settings: AppSettings) -> StoryDetail:
    flow.drop_story(db, auth.user, story_id)
    db.commit()
    return _detail(db, settings, story_id)
