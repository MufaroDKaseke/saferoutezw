"""Response and request models of the newsroom API (``/api/v1/newsroom``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel
from app.schemas.newsroom_workflow import StoryLink, WorkflowSummary

ArticleState = Literal["classified", "pending", "failed", "skipped"]
ReviewStatus = Literal["new", "reviewed", "used", "dismissed"]
Basis = Literal["full_text", "excerpt", "headline"]


class ArticleReview(ApiModel):
    status: ReviewStatus = "new"
    by: str | None = None  # display name of the editor who last set it
    at: datetime | None = None
    note: str | None = None


class ArticleSummary(ApiModel):
    id: uuid.UUID
    publisher_id: uuid.UUID
    publisher: str
    headline: str
    source_url: str | None
    published_at: datetime | None
    collected_at: datetime
    state: ArticleState
    processing_status: str
    category: str | None = Field(description="Primary news category value, once classified.")
    secondary_category: str | None
    summary: str | None
    geographic_relevance: str | None
    needs_editorial_attention: bool = False
    classification_basis: Basis | None
    review: ArticleReview


class ArticleDetail(ArticleSummary):
    excerpt: str | None
    article_text: str | None
    topics: list[str] = []
    organisations: list[str] = []
    places: list[str] = []
    attention_reason: str | None = None
    classification_confidence: float | None = Field(
        default=None, description="How clearly the text supports the category. Not the probability the article is true."
    )
    model: str | None = None
    prompt_version: str | None = None
    classified_at: datetime | None = None
    reused_from: uuid.UUID | None = None
    fetch_error: str | None = None
    last_error: str | None = None
    story: StoryLink | None = Field(default=None, description="The story built from this article, if one was taken.")


class CountBy(ApiModel):
    key: str
    label: str
    count: int


class PublisherCount(ApiModel):
    id: uuid.UUID
    name: str
    articles: int
    classified: int


class FeedHealth(ApiModel):
    enabled: int
    healthy: int
    unhealthy: int
    disabled: int


class UsageToday(ApiModel):
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None = Field(description="Only when per-million prices are configured; otherwise null.")


class NewsroomSummary(ApiModel):
    total_articles: int
    collected_today: int
    classified_today: int
    pending_classification: int
    failures: int
    feeds: FeedHealth
    usage_today: UsageToday
    by_category: list[CountBy]
    publishers: list[PublisherCount]
    workflow: WorkflowSummary
    generated_at: datetime


class CategoryOut(ApiModel):
    value: str
    label: str


class ReviewRequest(BaseModel):
    status: ReviewStatus
    note: str | None = Field(default=None, max_length=500)
