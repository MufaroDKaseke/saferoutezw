"""NUST FM story-to-air rules: reading time, who may touch a story, and every story state change.

Lifecycle: assigned -> drafting -> in_review -> approved (or changes_requested -> back to the reporter)
-> broadcast, with ``dropped`` as the way out. Every operation locks the story row, checks the caller
and the current stage, writes an audit event (ids and state only, never text) and flushes. The caller
commits. People stay in control: nothing here is automatic, and the database triggers back the rules up.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import APPROVER_ROLES, STORY_WRITE_ROLES, is_approver
from app.api.errors import ApiError, conflict, forbidden, not_found
from app.core.config import Settings
from app.models import Source, SourceItem, Story, StoryReview, StoryScript, User
from app.models.enums import CLOSED_STORY_STAGES, ScriptOrigin, StoryDecision, StoryStage, UserRole
from app.services.audit import record_audit

if TYPE_CHECKING:  # the API never imports OpenAI at startup: these modules are imported only inside draft_script
    from app.services.newsroom_script import ScriptDrafter

SCRIPT_EDITABLE_STAGES = (
    StoryStage.ASSIGNED.value,
    StoryStage.DRAFTING.value,
    StoryStage.CHANGES_REQUESTED.value,
    StoryStage.APPROVED.value,  # editing an approved story writes a new version and reopens it
)
VERIFIABLE_STAGES = (StoryStage.ASSIGNED.value, StoryStage.DRAFTING.value, StoryStage.CHANGES_REQUESTED.value)
# ``assigned`` is included so a story with nothing yet gets the useful answer (verify it, write a script)
# rather than a generic wrong-stage error; it can never pass those checks without a script, which starts drafting.
SUBMITTABLE_STAGES = (StoryStage.ASSIGNED.value, StoryStage.DRAFTING.value, StoryStage.CHANGES_REQUESTED.value)
CLOSED = tuple(s.value for s in CLOSED_STORY_STAGES)


def estimate_seconds(text: str, wpm: int) -> int:
    """Seconds needed to read ``text`` aloud at ``wpm`` words per minute, rounded up (0 for no words)."""
    words = len(text.split())
    return math.ceil(words * 60 / wpm) if words else 0


# ---- access -----------------------------------------------------------------------------------------------


def can_view(user: User, story: Story) -> bool:
    """Reporters see their own stories; the Executive Producer, admins and analysts see all of them."""
    return user.role != UserRole.REPORTER.value or story.assignee_id == user.id


def require_view(user: User, story: Story) -> None:
    if not can_view(user, story):
        raise forbidden("This story belongs to another reporter.")


def _require_write(user: User, story: Story) -> None:
    """Writers act on their own stories; the Executive Producer (approver roles) acts on all of them."""
    if not user.is_active or user.role not in {r.value for r in STORY_WRITE_ROLES}:
        raise forbidden()
    if not is_approver(user) and story.assignee_id != user.id:
        raise forbidden("This story belongs to another reporter.")


def _lock_story(session: Session, story_id: uuid.UUID) -> Story:
    story = session.get(Story, story_id, with_for_update=True, populate_existing=True)
    if story is None:
        raise not_found("STORY_NOT_FOUND", "No such story.")
    return story


def get_writable_story(session: Session, user: User, story_id: uuid.UUID) -> Story:
    story = _lock_story(session, story_id)
    _require_write(user, story)
    return story


def latest_script(session: Session, story_id: uuid.UUID) -> StoryScript | None:
    return session.scalar(
        select(StoryScript).where(StoryScript.story_id == story_id).order_by(StoryScript.version_number.desc()).limit(1)
    )


def _wrong_stage(story: Story, doing: str) -> ApiError:
    return conflict("INVALID_STAGE", f"A story that is {story.stage.replace('_', ' ')} cannot be {doing}.")


def _validate_assignee(session: Session, assignee_id: uuid.UUID) -> User:
    assignee = session.get(User, assignee_id)
    if assignee is None or not assignee.is_active or assignee.role not in {r.value for r in STORY_WRITE_ROLES}:
        raise ApiError(422, "INVALID_ASSIGNEE", "A story can only be assigned to an active reporter or editor.")
    return assignee


# ---- operations -----------------------------------------------------------------------------------------------


def create_story(
    session: Session,
    user: User,
    *,
    title: str | None,
    source_item_id: uuid.UUID | None,
    assignee_id: uuid.UUID | None,
    deadline_at: datetime | None,
    follows_story_id: uuid.UUID | None,
) -> Story:
    """Take an article (or start an original story). Reporters assign themselves; the EP can assign anyone."""
    if not user.is_active or user.role not in {r.value for r in STORY_WRITE_ROLES}:
        raise forbidden()
    if assignee_id is not None and assignee_id != user.id and not is_approver(user):
        raise forbidden("Only the Executive Producer can assign a story to someone else.")
    assignee = _validate_assignee(session, assignee_id or user.id)

    item = None
    if source_item_id is not None:
        item = session.get(SourceItem, source_item_id)
        if item is None:
            raise not_found("ARTICLE_NOT_FOUND", "No such article.")
    title = title or (item.title_redacted.strip() if item is not None else None)
    if not title:
        raise ApiError(422, "TITLE_REQUIRED", "Give the story a title.")
    if follows_story_id is not None and session.get(Story, follows_story_id) is None:
        raise not_found("STORY_NOT_FOUND", "The story to follow up does not exist.")

    story = Story(
        source_item_id=source_item_id,
        title=title,
        stage=StoryStage.ASSIGNED.value,
        assignee_id=assignee.id,
        deadline_at=deadline_at,
        follows_story_id=follows_story_id,
    )
    try:
        with session.begin_nested():  # the unique index is the final word if two people take it at once
            session.add(story)
            session.flush()
    except IntegrityError:
        raise conflict("ARTICLE_ALREADY_HAS_STORY", "Someone has already taken this article.") from None
    record_audit(
        session,
        actor_id=user.id,
        action="newsroom.story_created",
        entity_type="story",
        entity_id=story.id,
        details={
            "stage": story.stage,
            "assignee_id": str(assignee.id),
            "source_item_id": str(source_item_id) if source_item_id else None,
        },
    )
    return story


def update_story(session: Session, user: User, story_id: uuid.UUID, changes: dict) -> Story:
    """Change title, deadline or assignee (``changes`` holds only the fields the caller sent)."""
    story = get_writable_story(session, user, story_id)
    if story.stage in CLOSED:
        raise _wrong_stage(story, "changed")
    changed: dict[str, object] = {}
    if "title" in changes and changes["title"] is not None and changes["title"] != story.title:
        story.title = changes["title"]
        changed["title"] = True
    if "deadline_at" in changes and changes["deadline_at"] != story.deadline_at:
        story.deadline_at = changes["deadline_at"]
        changed["deadline_at"] = True
    new_assignee = changes.get("assignee_id")
    if new_assignee is not None and new_assignee != story.assignee_id:
        if not is_approver(user):
            raise forbidden("Only the Executive Producer can reassign a story.")
        assignee = _validate_assignee(session, new_assignee)
        changed["assignee"] = {"from": str(story.assignee_id), "to": str(assignee.id)}
        story.assignee_id = assignee.id
    session.flush()
    if changed:
        record_audit(
            session, actor_id=user.id, action="newsroom.story_updated", entity_type="story", entity_id=story.id,
            details={"changes": changed},
        )
    return story


def record_verification(session: Session, user: User, story_id: uuid.UUID, note: str) -> Story:
    """The reporter records how the facts were checked. Required before submitting or asking for an AI draft."""
    story = get_writable_story(session, user, story_id)
    if story.stage not in VERIFIABLE_STAGES:
        raise _wrong_stage(story, "verified")
    story.verification_note = note
    story.verified_at = datetime.now(UTC)
    story.verified_by = user.id
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.story_verified", entity_type="story", entity_id=story.id,
        details={},
    )
    return story


@dataclass(frozen=True)
class AiDraftMeta:
    """Which model wrote an AI draft, from which prompt, at what token cost. Kept on the script row."""

    model_name: str
    prompt_version: str
    input_tokens: int | None
    output_tokens: int | None


def _check_base_version(current: StoryScript | None, base_version: int | None) -> int | None:
    current_number = current.version_number if current else None
    if base_version != current_number:
        raise conflict(
            "SCRIPT_VERSION_CONFLICT", "Someone else saved a newer version of this script. Reload before saving."
        )
    return current_number


def save_script(
    session: Session,
    settings: Settings,
    user: User,
    story_id: uuid.UUID,
    *,
    headline: str,
    body: str,
    base_version: int | None,
    ai: AiDraftMeta | None = None,
) -> tuple[Story, StoryScript]:
    """Write the next script version. Older versions are never changed.

    ``base_version`` is the version the caller was editing (``None`` for the first script): if someone
    saved a newer one meanwhile, nothing is overwritten and the caller must reload. ``ai`` marks a draft
    the model wrote; a person's edit of it is saved as a normal (human) version.
    """
    story = get_writable_story(session, user, story_id)
    if story.stage not in SCRIPT_EDITABLE_STAGES:
        raise _wrong_stage(story, "edited")
    current_number = _check_base_version(latest_script(session, story.id), base_version)
    script = StoryScript(
        story_id=story.id,
        version_number=(current_number or 0) + 1,
        headline=headline,
        body=body,
        estimated_seconds=estimate_seconds(body, settings.newsroom_reading_wpm),
        origin=ScriptOrigin.AI_DRAFT.value if ai else ScriptOrigin.HUMAN.value,
        model_name=ai.model_name if ai else None,
        prompt_version=ai.prompt_version if ai else None,
        input_tokens=ai.input_tokens if ai else None,
        output_tokens=ai.output_tokens if ai else None,
        created_by=user.id,
    )
    session.add(script)
    reopened = story.stage == StoryStage.APPROVED.value
    if story.stage in (StoryStage.ASSIGNED.value, StoryStage.APPROVED.value):
        # The first script starts drafting; an edit after approval puts the story back in front of an editor.
        # The approved version itself is untouched, and stays the live one until the new one is approved.
        story.stage = StoryStage.DRAFTING.value
    session.flush()
    details: dict[str, object] = {
        "script_id": str(script.id), "version": script.version_number, "origin": script.origin,
        "estimated_seconds": script.estimated_seconds, "reopened": reopened,
    }
    if ai:
        details.update(model=ai.model_name, prompt_version=ai.prompt_version,
                       input_tokens=ai.input_tokens, output_tokens=ai.output_tokens)
    record_audit(
        session, actor_id=user.id, action="newsroom.script_saved", entity_type="story", entity_id=story.id,
        details=details,
    )
    return story, script


def draft_script(
    session: Session,
    settings: Settings,
    user: User,
    story_id: uuid.UUID,
    drafter: ScriptDrafter,
    *,
    base_version: int | None,
    target_seconds: int,
) -> tuple[Story, StoryScript]:
    """Ask the model for a first draft of the script, on a reporter's request only.

    Needs a recorded verification and a source article. Only the redacted article text goes to the model. The
    result is saved as an ``ai_draft`` version; the reporter edits it, and an editor still has to approve it.
    The model call can take seconds, so the story row is not locked while it runs: the save at the end locks it
    and re-checks the stage and ``base_version``.
    """
    from app.services.extraction import ExtractionError, ExtractionInput, ExtractorUnavailable  # lazy: pulls in the OpenAI SDK

    story = session.get(Story, story_id)
    if story is None:
        raise not_found("STORY_NOT_FOUND", "No such story.")
    _require_write(user, story)
    if story.stage not in SCRIPT_EDITABLE_STAGES:
        raise _wrong_stage(story, "edited")
    if story.verified_at is None:
        raise conflict("NOT_VERIFIED", "Record how the story was verified before asking for an AI draft.")
    if story.source_item_id is None:
        raise conflict("NO_SOURCE_ARTICLE", "This story has no article to draft from. Write the script by hand.")
    _check_base_version(latest_script(session, story.id), base_version)  # before spending money on the model

    found = session.execute(
        select(SourceItem, Source.name).join(Source, Source.id == SourceItem.source_id).where(SourceItem.id == story.source_item_id)
    ).first()
    if found is None:
        raise not_found("ARTICLE_NOT_FOUND", "No such article.")
    item, publisher = found
    text = (item.article_text_redacted or "").strip() or (item.excerpt_redacted or "").strip()
    if not text:
        raise conflict("NO_ARTICLE_TEXT", "No article text was stored, so there is nothing to draft from.")
    note = None if (item.article_text_redacted or "").strip() else "Only the feed excerpt is available."

    try:
        out = drafter.draft(
            ExtractionInput(
                source_name=publisher, title=item.title_redacted, published=item.published_at, text=text, note=note
            ),
            target_seconds,
        )
    except ExtractorUnavailable:
        raise ApiError(
            503,
            "AI_DRAFTING_UNAVAILABLE",
            "AI drafting is not available right now. Write the script by hand, or ask an administrator to check the OpenAI key.",
        ) from None
    except ExtractionError:
        raise ApiError(
            502, "AI_DRAFT_FAILED", "The AI draft could not be produced. Try again, or write the script by hand."
        ) from None

    return save_script(
        session,
        settings,
        user,
        story_id,
        headline=out.headline,
        body=out.body,
        base_version=base_version,
        ai=AiDraftMeta(out.model, out.prompt_version, out.input_tokens, out.output_tokens),
    )


def submit_story(session: Session, user: User, story_id: uuid.UUID) -> Story:
    story = get_writable_story(session, user, story_id)
    if story.stage not in SUBMITTABLE_STAGES:
        raise _wrong_stage(story, "submitted")
    if story.verified_at is None:
        raise conflict("NOT_VERIFIED", "Record how the story was verified before submitting it.")
    script = latest_script(session, story.id)
    if script is None:
        raise conflict("NO_SCRIPT", "Write a script before submitting the story.")
    story.stage = StoryStage.IN_REVIEW.value
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.story_submitted", entity_type="story", entity_id=story.id,
        details={"script_version": script.version_number},
    )
    return story


def review_story(
    session: Session,
    user: User,
    story_id: uuid.UUID,
    *,
    decision: str,
    script_version: int,
    comment: str | None,
) -> Story:
    """Approve the submitted script or send it back. Only approver roles; reporters can never approve."""
    if not user.is_active or user.role not in {r.value for r in APPROVER_ROLES}:
        raise forbidden("Only the Executive Producer can approve or send back a story.")
    story = _lock_story(session, story_id)
    if story.stage != StoryStage.IN_REVIEW.value:
        raise conflict("INVALID_STAGE", "Only a story that has been submitted can be approved or sent back.")
    script = latest_script(session, story.id)
    if script is None or script.version_number != script_version:
        raise conflict("STALE_SCRIPT", "The script changed since you opened it. Reload and review the newest version.")
    comment = (comment or "").strip() or None
    if decision == StoryDecision.CHANGES_REQUESTED.value and comment is None:
        raise ApiError(422, "COMMENT_REQUIRED", "Say what needs to change when sending a story back.")

    approved = decision == StoryDecision.APPROVED.value
    # Reporters can never reach this point; the Executive Producer approving their own work is allowed but flagged.
    self_approved = approved and user.id in (story.assignee_id, script.created_by)
    review = StoryReview(
        story_id=story.id,
        script_id=script.id,
        reviewer_id=user.id,
        decision=decision,
        comment=comment,
        self_approved=self_approved,
    )
    session.add(review)
    session.flush()  # the database guard on stories.stage looks for this review
    story.stage = StoryStage.APPROVED.value if approved else StoryStage.CHANGES_REQUESTED.value
    session.flush()
    record_audit(
        session, actor_id=user.id,
        action="newsroom.story_approved" if approved else "newsroom.story_sent_back",
        entity_type="story", entity_id=story.id,
        details={"script_version": script.version_number, "review_id": str(review.id), "self_approved": self_approved},
    )
    return story


def drop_story(session: Session, user: User, story_id: uuid.UUID) -> Story:
    story = get_writable_story(session, user, story_id)
    if story.stage in CLOSED:
        raise _wrong_stage(story, "dropped")
    previous = story.stage
    story.stage = StoryStage.DROPPED.value
    session.flush()
    record_audit(
        session, actor_id=user.id, action="newsroom.story_dropped", entity_type="story", entity_id=story.id,
        details={"previous_stage": previous},
    )
    return story
