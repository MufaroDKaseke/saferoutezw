"""Builders for the NUST FM newsroom tests: a newsroom-mode client, a fake classifier and article factories.

Everything is synthetic. The classifier is a fake, so no test calls OpenAI or costs money.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

import db_factories as f
from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.newsroom import NewsClassification
from app.services.extraction import ExtractionError, ExtractionInput
from app.services.newsroom_extraction import NEWSROOM_PROMPT_VERSION, NewsroomOutput
from public_helpers import make_settings


def classification(**overrides: Any) -> dict[str, Any]:
    """A valid newsroom classification reply (a politics story); override any field."""
    reply: dict[str, Any] = {
        "primary_category": "politics_governance",
        "secondary_category": None,
        "summary": "Parliament debated the national budget.",
        "topics": ["budget", "parliament"],
        "organisations": ["Parliament of Zimbabwe"],
        "places": ["Harare"],
        "geographic_relevance": "zimbabwe_wide",
        "classification_confidence": 0.9,
        "needs_editorial_attention": False,
        "attention_reason": None,
    }
    reply.update(overrides)
    return reply


class FakeNewsroomExtractor:
    """Stands in for the OpenAI newsroom classifier. Give it replies (dicts) or exceptions, in order."""

    kind = "newsroom"
    model_name = "fake-newsroom-model"

    def __init__(self, *replies: Any, default: dict[str, Any] | None = None):
        self.replies = list(replies)
        self.default = default
        self.calls: list[ExtractionInput] = []

    def extract(self, item: ExtractionInput) -> NewsroomOutput:
        self.calls.append(item)
        reply = self.replies.pop(0) if self.replies else (self.default if self.default is not None else classification())
        if isinstance(reply, Exception):
            raise reply
        return NewsroomOutput(
            classification=NewsClassification.model_validate(reply),
            model="fake-newsroom-model-1",
            prompt_version=NEWSROOM_PROMPT_VERSION,
            input_tokens=120,
            output_tokens=60,
        )


def retryable_error(message: str = "OpenAI call failed: RateLimitError") -> ExtractionError:
    return ExtractionError(message, retryable=True)


def classified_metadata(reply: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    """``source_metadata`` as the pipeline leaves it after a successful classification."""
    body = dict(reply or classification())
    body.update({"basis": "full_text", "model": "fake-newsroom-model-1", "prompt_version": NEWSROOM_PROMPT_VERSION,
                 "at": datetime.now(UTC).isoformat()})
    return {"url": "https://example.test/a", "classification": body, **extra}


def make_article(session, source=None, *, status="processed", reply=None, metadata=None, **overrides):
    """A ``source_items`` row. ``status='processed'`` gets a classification; other statuses stay unclassified."""
    source = source or f.make_source(session)
    if metadata is None:
        metadata = classified_metadata(reply) if status == "processed" else {"url": "https://example.test/a"}
    item = f.make_source_item(session, source, processing_status=status, source_metadata=metadata, **overrides)
    session.commit()
    return item


@pytest.fixture
def newsroom_client(session):
    """API client for an app built in ``nust_newsroom`` mode, sharing the test's database session."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    settings = make_settings(app_mode="nust_newsroom", newsroom_price_input_per_1m=0.15, newsroom_price_output_per_1m=0.60)
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
