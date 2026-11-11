"""General news classification for the NUST FM newsroom mode (``APP_MODE=nust_newsroom``).

One structured reply per article: a primary category (and optionally a secondary one), a short
grounded summary, topics, organisations and places that the article itself names, how local the story
is, and whether an editor should look at it. Everything is an *unverified machine reading* of the text:

* ``classification_confidence`` says how clearly the article supports the chosen category. It is NOT the
  probability that the article is true, and nothing here checks facts.
* The original headline, publisher and URL are never produced by the model; they stay on the source item.

Fields are required-but-nullable so the JSON schema works with Structured Outputs strict mode, and every
value is validated again here because the model is not trusted.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, field_validator, model_validator

from app.schemas.intelligence import _Block, _strictify


class NewsCategory(StrEnum):
    POLITICS_GOVERNANCE = "politics_governance"
    BUSINESS_ECONOMY = "business_economy"
    EDUCATION = "education"
    HEALTH = "health"
    TECHNOLOGY = "technology"
    SPORTS = "sports"
    ENTERTAINMENT_CULTURE = "entertainment_culture"
    CRIME_COURTS = "crime_courts"
    TRANSPORT_INFRASTRUCTURE = "transport_infrastructure"
    ENVIRONMENT_AGRICULTURE = "environment_agriculture"
    COMMUNITY_LOCAL = "community_local"
    INTERNATIONAL = "international"
    OTHER = "other"


NEWS_CATEGORY_LABELS: dict[str, str] = {
    "politics_governance": "Politics & Governance",
    "business_economy": "Business & Economy",
    "education": "Education",
    "health": "Health",
    "technology": "Technology",
    "sports": "Sports",
    "entertainment_culture": "Entertainment & Culture",
    "crime_courts": "Crime & Courts",
    "transport_infrastructure": "Transport & Infrastructure",
    "environment_agriculture": "Environment & Agriculture",
    "community_local": "Community & Local News",
    "international": "International News",
    "other": "Other / Unclassified",
}


class GeographicRelevance(StrEnum):
    BULAWAYO = "bulawayo"
    MATABELELAND = "matabeleland"
    ZIMBABWE_WIDE = "zimbabwe_wide"
    INTERNATIONAL = "international"
    UNCLEAR = "unclear"


GEOGRAPHIC_RELEVANCE_LABELS: dict[str, str] = {
    "bulawayo": "Bulawayo",
    "matabeleland": "Matabeleland",
    "zimbabwe_wide": "Zimbabwe-wide",
    "international": "International",
    "unclear": "Unclear",
}

# Where the classifier read from. "excerpt" means the full article could not be retrieved.
BASIS_FULL_TEXT = "full_text"
BASIS_EXCERPT = "excerpt"


class NewsClassification(_Block):
    primary_category: NewsCategory
    secondary_category: NewsCategory | None = Field(description="Only when the article clearly belongs to two areas; otherwise null.")
    summary: str = Field(
        max_length=700,
        description="Neutral 1-3 sentence summary using only facts stated in the article. No opinion, no invented detail.",
    )
    topics: list[str] = Field(max_length=8, description="Short topic keywords taken from the article.")
    organisations: list[str] = Field(max_length=8, description="Organisations the article names. Empty if none.")
    places: list[str] = Field(max_length=8, description="Places the article names. Empty if none.")
    geographic_relevance: GeographicRelevance
    classification_confidence: float = Field(
        ge=0, le=1, description="How clearly the text supports the category. NOT the probability the article is true."
    )
    needs_editorial_attention: bool = Field(
        description="True for sensitive, unclear, unverified or potentially defamatory material an editor should read first."
    )
    attention_reason: str | None = Field(max_length=240, description="One short reason when needs_editorial_attention is true.")

    @field_validator("topics", "organisations", "places", mode="after")
    @classmethod
    def _clean_list(cls, values: list[str]) -> list[str]:
        cleaned = [" ".join(v.split()) for v in values if isinstance(v, str) and v.strip()]
        return list(dict.fromkeys(cleaned))

    @field_validator("summary", mode="after")
    @classmethod
    def _summary_not_blank(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("summary is blank")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> NewsClassification:
        if self.secondary_category == self.primary_category:
            self.secondary_category = None
        if not self.needs_editorial_attention:
            self.attention_reason = None
        return self

    def stored(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def build_json_schema() -> dict[str, Any]:
    return _strictify(NewsClassification.model_json_schema())


NEWS_JSON_SCHEMA: dict[str, Any] = build_json_schema()
