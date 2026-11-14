"""Request and response models of the NUST FM story-to-air workflow (``/api/v1/newsroom/stories``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.schemas.common import ApiModel

StoryStageName = Literal["assigned", "drafting", "in_review", "changes_requested", "approved", "broadcast", "dropped"]
ScriptOriginName = Literal["human", "ai_draft"]
DecisionName = Literal["approved", "changes_requested"]

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
ScriptBody = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class Person(ApiModel):
    id: uuid.UUID
    display_name: str


class Assignee(Person):
    role: str


class ArticleLink(ApiModel):
    id: uuid.UUID
    headline: str
    publisher: str
    source_url: str | None
    published_at: datetime | None


class StoryLink(ApiModel):
    """A pointer to a story, shown on the article page."""

    id: uuid.UUID
    title: str
    stage: StoryStageName
    assignee: Person


class StorySummary(ApiModel):
    id: uuid.UUID
    title: str
    stage: StoryStageName
    assignee: Person
    deadline_at: datetime | None
    source_item_id: uuid.UUID | None
    article_headline: str | None
    verified: bool
    latest_script_version: int | None
    latest_script_seconds: int | None = Field(description="Estimated reading time of the newest script, in seconds.")
    approved_script_version: int | None = Field(description="The script version a person approved, if any.")
    follows_story_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class Verification(ApiModel):
    note: str
    at: datetime
    by: Person


class ScriptOut(ApiModel):
    id: uuid.UUID
    version_number: int
    headline: str
    body: str
    estimated_seconds: int
    origin: ScriptOriginName
    model_name: str | None
    prompt_version: str | None
    created_by: Person
    created_at: datetime


class StoryReviewOut(ApiModel):
    id: uuid.UUID
    script_id: uuid.UUID
    script_version: int
    decision: DecisionName
    comment: str | None
    self_approved: bool
    reviewer: Person
    reviewed_at: datetime


class StoryDetail(StorySummary):
    verification: Verification | None
    article: ArticleLink | None
    scripts: list[ScriptOut]
    reviews: list[StoryReviewOut]
    reading_wpm: int = Field(description="Words per minute behind every reading-time estimate.")


# ---- requests ------------------------------------------------------------------------------------------


class StoryCreate(BaseModel):
    title: Title | None = Field(default=None, description="Defaults to the article headline when an article is given.")
    source_item_id: uuid.UUID | None = None
    assignee_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the caller. Only the Executive Producer may assign someone else."
    )
    deadline_at: datetime | None = None
    follows_story_id: uuid.UUID | None = None


class StoryUpdate(BaseModel):
    title: Title | None = None
    assignee_id: uuid.UUID | None = None
    deadline_at: datetime | None = None  # send null to clear the deadline


class VerifyRequest(BaseModel):
    note: Note = Field(description="How the facts were checked.")


class ScriptCreate(BaseModel):
    headline: Title
    body: ScriptBody
    base_version: int | None = Field(
        default=None,
        ge=1,
        description="The version being edited; null for a story's first script. Refused if a newer one exists.",
    )


class DraftRequest(BaseModel):
    """Ask the model for a first draft. Never automatic: this is the button the reporter presses."""

    target_seconds: int | None = Field(
        default=None, ge=10, le=600, description="How long the script should take to read aloud. Defaults to 45 seconds."
    )
    base_version: int | None = Field(
        default=None, ge=1, description="The script version on screen; null for a story with no script yet."
    )


class StoryDecisionRequest(BaseModel):
    decision: DecisionName
    script_version: int = Field(ge=1, description="The script version the reviewer was looking at.")
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None = None


# ---- radio bulletins ----------------------------------------------------------------------------------------------

RevisionStateName = Literal["draft", "pending_approval", "approved", "superseded", "rejected"]
BulletinDecisionName = Literal["approved", "rejected"]

OptionalComment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None


class StoryRef(ApiModel):
    id: uuid.UUID
    title: str
    stage: StoryStageName


class ScriptRef(ApiModel):
    id: uuid.UUID
    version_number: int
    headline: str
    estimated_seconds: int


class BulletinItemOut(ApiModel):
    position: int
    story: StoryRef
    script: ScriptRef
    script_approved: bool = Field(description="The pinned script version carries an approving review.")
    newer_script_version: int | None = Field(
        description="The story has been rewritten since this version was pinned. Only a flag: the pinned version is still what is read."
    )
    duration_seconds: int = Field(description="The override for a clip, otherwise the script's reading-time estimate.")
    duration_overridden: bool
    note: str | None


class BulletinDecisionOut(ApiModel):
    decision: BulletinDecisionName
    comment: str | None
    self_approved: bool
    reviewer: Person
    decided_at: datetime


class RevisionOut(ApiModel):
    id: uuid.UUID
    revision_number: int
    state: RevisionStateName
    items: list[BulletinItemOut]
    total_seconds: int
    created_by: Person
    created_at: datetime
    submitted_by: Person | None
    submitted_at: datetime | None
    approved_by: Person | None
    approved_at: datetime | None
    aired_by: Person | None
    aired_at: datetime | None
    decisions: list[BulletinDecisionOut]


class BulletinSummary(ApiModel):
    id: uuid.UUID
    name: str
    scheduled_for: datetime
    target_seconds: int
    approved_revision_number: int | None
    approved_at: datetime | None
    approved_total_seconds: int | None
    latest_revision_number: int
    latest_revision_state: RevisionStateName
    aired_at: datetime | None
    created_by: Person
    created_at: datetime


class BulletinDetail(BulletinSummary):
    revisions: list[RevisionOut]


class BulletinCreate(BaseModel):
    name: Title
    scheduled_for: AwareDatetime
    target_seconds: int = Field(ge=10, le=7200, description="How long the bulletin should run, in seconds.")


class BulletinItemInput(BaseModel):
    story_id: uuid.UUID
    script_id: uuid.UUID | None = Field(
        default=None, description="Defaults to the story's approved script, or its newest if none is approved yet."
    )
    duration_override_seconds: int | None = Field(default=None, ge=1, le=3600, description="For a clip.")
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class BulletinItemsUpdate(BaseModel):
    items: list[BulletinItemInput] = Field(max_length=60, description="The whole running order, in order.")


class BulletinApproveRequest(BaseModel):
    comment: OptionalComment = None


class BulletinRejectRequest(BaseModel):
    comment: Note = Field(description="What needs to change. Required.")


# ---- studio view ----------------------------------------------------------------------------------------------------


class StudioItem(ApiModel):
    position: int
    story_title: str
    headline: str
    body: str
    duration_seconds: int
    duration_overridden: bool
    note: str | None


class StudioView(ApiModel):
    """What the studio screen shows. Always read from the server record, never cached: the screen must say it
    cannot confirm when it cannot get this answer."""

    bulletin_id: uuid.UUID
    name: str
    scheduled_for: datetime
    target_seconds: int
    status: Literal["approved", "not_approved"] = Field(description="Whether the bulletin has an approved revision to read from.")
    version: int | None = Field(description="The approved revision number: the version to read.")
    approved_at: datetime | None
    approved_by: Person | None
    items: list[StudioItem]
    total_seconds: int
    newer_revision_pending: bool = Field(
        description="A newer revision has been submitted and awaits approval. The approved version above is still the live one."
    )
    newer_revision_number: int | None
    aired_at: datetime | None
    server_time: datetime


# ---- archive -----------------------------------------------------------------------------------------------------------


class ArchiveBulletinRef(ApiModel):
    id: uuid.UUID
    name: str
    revision_number: int
    aired_at: datetime


class ArchiveStoryLink(ApiModel):
    """A pointer to another story in the archive (follow-ups)."""

    id: uuid.UUID
    title: str
    aired_at: datetime


class ArchiveStory(ApiModel):
    id: uuid.UUID
    title: str
    headline: str = Field(description="The headline of the script version that went to air.")
    excerpt: str = Field(description="The start of the aired script.")
    category: str | None
    category_label: str | None
    aired_at: datetime = Field(description="When it first went to air.")
    last_aired_at: datetime
    bulletins: list[ArchiveBulletinRef]
    reporter: Person
    follows: ArchiveStoryLink | None
    follow_up_count: int
    publisher: str | None
    source_url: str | None


class ArchiveScript(ApiModel):
    version_number: int
    headline: str
    body: str
    estimated_seconds: int
    origin: ScriptOriginName
    created_by: Person
    created_at: datetime
    aired_in: list[ArchiveBulletinRef]


class ArchiveVersion(ApiModel):
    version_number: int
    origin: ScriptOriginName
    created_by: Person
    created_at: datetime
    approved: bool
    aired: bool


class ArchiveReview(ApiModel):
    script_version: int
    decision: DecisionName
    comment: str | None
    self_approved: bool
    reviewer: Person
    reviewed_at: datetime


class ArchiveStoryDetail(ArchiveStory):
    source_item_id: uuid.UUID | None
    scripts: list[ArchiveScript] = Field(description="Every script version that went to air, with its text.")
    versions: list[ArchiveVersion] = Field(description="The whole version history. Only aired versions carry text, in `scripts`.")
    reviews: list[ArchiveReview]
    followed_by: list[ArchiveStoryLink]


class ArchiveBulletin(ApiModel):
    id: uuid.UUID
    name: str
    scheduled_for: datetime
    revision_number: int
    aired_at: datetime
    aired_by: Person
    total_seconds: int
    story_count: int


class ArchiveBulletinItem(StudioItem):
    story_id: uuid.UUID


class ArchiveBulletinDetail(ArchiveBulletin):
    target_seconds: int
    approved_at: datetime | None
    approved_by: Person | None
    items: list[ArchiveBulletinItem]


# ---- dashboard ---------------------------------------------------------------------------------------------------------


class WorkflowSummary(ApiModel):
    stories_awaiting_approval: int
    stories_in_progress: int = Field(description="Stories that are neither broadcast nor dropped.")
    bulletins_awaiting_approval: int
    next_bulletin: BulletinSummary | None = Field(description="The soonest bulletin that has not gone to air yet.")
