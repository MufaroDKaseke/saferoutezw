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
from app.services.newsroom_script import NEWSROOM_SCRIPT_PROMPT_VERSION, ScriptOutput
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


N = "/api/v1/newsroom"
S = f"{N}/stories"


def make_staff(session, role: str):
    """A newsroom user (reporter, editor = Executive Producer, analyst, admin) who can sign in."""
    from api_helpers import make_login_user

    user = make_login_user(session, role)
    session.commit()
    return user


def login_as(client, user) -> dict[str, str]:
    """Sign ``user`` in on ``client`` (replacing whoever was signed in) and return the CSRF header for writes."""
    from api_helpers import PASSWORD

    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"X-CSRF-Token": response.json()["csrf_token"]}


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


# ---- story workflow ---------------------------------------------------------------------------------------------


def words(n: int) -> str:
    return " ".join(["word"] * n)


class Room:
    """One reporter, a second reporter, the Executive Producer (editor role) and an analyst, on one client."""

    def __init__(self, client, session):
        self.client, self.session = client, session
        self.reporter = make_staff(session, "reporter")
        self.other = make_staff(session, "reporter")
        self.ep = make_staff(session, "editor")
        self.analyst = make_staff(session, "analyst")
        self.headers: dict[str, str] = {}

    def as_(self, user):
        self.headers = login_as(self.client, user)
        return self

    def get(self, path, **kw):
        return self.client.get(path, **kw)

    def post(self, path, body=None, **kw):
        return self.client.post(path, json=body, headers=self.headers, **kw)

    def patch(self, path, body):
        return self.client.patch(path, json=body, headers=self.headers)

    def take(self, user, article=None, **body):
        """``user`` takes an article (or starts an original story); returns the new story's id."""
        self.as_(user)
        if article is not None:
            body["source_item_id"] = str(article.id)
        else:
            body.setdefault("title", "Original story")
        response = self.post(S, body)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def verify(self, story_id, note="Called the council spokesperson and checked the original statement."):
        response = self.post(f"{S}/{story_id}/verify", {"note": note})
        assert response.status_code == 200, response.text

    def script(self, story_id, body=None, headline="Council approves budget", base=None):
        response = self.post(
            f"{S}/{story_id}/scripts", {"headline": headline, "body": body or words(75), "base_version": base}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def submit(self, story_id):
        response = self.post(f"{S}/{story_id}/submit")
        assert response.status_code == 200, response.text
        return response.json()

    def review(self, story_id, version, decision="approved", comment=None):
        return self.post(
            f"{S}/{story_id}/review", {"decision": decision, "script_version": version, "comment": comment}
        )

    def ready_for_review(self, user=None, article=None):
        """A story the reporter has verified, scripted and submitted. Returns its id."""
        story_id = self.take(user or self.reporter, article)
        self.verify(story_id)
        self.script(story_id)
        self.submit(story_id)
        return story_id


@pytest.fixture
def room(newsroom_client, session):
    return Room(newsroom_client, session)


# ---- AI script drafting ---------------------------------------------------------------------------------------


class FakeScriptDrafter:
    """Stands in for the OpenAI script drafter. Give it replies (``ScriptOutput`` or exceptions), in order.

    With no replies it returns a short, valid script. Records every call so a test can assert what the model
    was (and was not) sent, and that it was not called at all when a request is refused earlier.
    """

    kind = "newsroom_script"
    model_name = "fake-script-model"

    def __init__(self, *replies: Any, input_tokens: int = 200, output_tokens: int = 100):
        self.replies = list(replies)
        self.input_tokens, self.output_tokens = input_tokens, output_tokens
        self.calls: list[tuple[ExtractionInput, int]] = []

    def draft(self, item: ExtractionInput, target_seconds: int) -> ScriptOutput:
        self.calls.append((item, target_seconds))
        reply = self.replies.pop(0) if self.replies else None
        if isinstance(reply, Exception):
            raise reply
        if reply is not None:
            return reply
        return ScriptOutput(
            headline="Council approves budget",
            body="The Bulawayo city council has approved its budget, according to The Herald. " + words(30),
            model="fake-script-model-1",
            prompt_version=NEWSROOM_SCRIPT_PROMPT_VERSION,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


@pytest.fixture
def drafter(newsroom_client):
    """The fake drafter, installed in place of the real one for this test."""
    from app.api.v1.newsroom_stories import get_script_drafter

    fake = FakeScriptDrafter()
    newsroom_client.app.dependency_overrides[get_script_drafter] = lambda: fake
    return fake


def fake_openai_client(reply: Any, *, usage=(321, 87), model="gpt-script-2026"):
    """An ``openai.OpenAI``-shaped client whose single reply is ``reply`` (a dict, or raw text)."""
    import json
    from types import SimpleNamespace

    class Completions:
        def __init__(self):
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            content = reply if isinstance(reply, str) else json.dumps(reply)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content, refusal=None), finish_reason="stop")],
                model=model,
                usage=SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1]),
            )

    completions = Completions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client.completions = completions  # for assertions
    return client


# ---- radio bulletins ---------------------------------------------------------------------------------------------


B = f"{N}/bulletins"
AIR = "2099-01-01T16:00:00Z"


def make_bulletin(room, **overrides):
    room.as_(room.ep)
    body = {"name": "6pm News", "scheduled_for": AIR, "target_seconds": 300, **overrides}
    response = room.post(B, body)
    assert response.status_code == 201, response.text
    return response.json()


def approved_story(room, session, script_body=None, article=True, headline="Council approves budget", **article_overrides):
    """A story whose script version 1 is approved. Returns (story_id, script_id).

    ``article_overrides`` go to ``make_article`` (for example ``reply=classification(primary_category="sports")``)."""
    story_id = room.take(room.reporter, make_article(session, **article_overrides) if article else None, **({} if article else {"title": headline}))
    room.verify(story_id)
    room.script(story_id, body=script_body, headline=headline)
    room.submit(story_id)
    room.as_(room.ep)
    approved = room.review(story_id, 1)
    assert approved.status_code == 200, approved.text
    return story_id, approved.json()["scripts"][0]["id"]


def put_items(room, bulletin_id, number, items):
    return room.client.put(f"{B}/{bulletin_id}/revisions/{number}/items", json={"items": items}, headers=room.headers)


def revision_action(room, bulletin_id, number, action, body=None):
    return room.post(f"{B}/{bulletin_id}/revisions/{number}/{action}", body)


def ready_bulletin(room, session, stories=2, **overrides):
    """A bulletin whose revision 1 holds approved stories and is waiting for approval. Returns (bulletin, [story ids])."""
    bulletin = make_bulletin(room, **overrides)
    ids = [approved_story(room, session)[0] for _ in range(stories)]
    room.as_(room.ep)
    assert put_items(room, bulletin["id"], 1, [{"story_id": i} for i in ids]).status_code == 200
    assert revision_action(room, bulletin["id"], 1, "submit").status_code == 200
    return bulletin, ids


def live_bulletin(room, session, stories=2, **overrides):
    """A bulletin whose revision 1 is approved and live."""
    bulletin, ids = ready_bulletin(room, session, stories, **overrides)
    assert revision_action(room, bulletin["id"], 1, "approve").status_code == 200
    return bulletin, ids


def revision(detail, number):
    return next(r for r in detail["revisions"] if r["revision_number"] == number)


def states(detail):
    return {r["revision_number"]: r["state"] for r in detail["revisions"]}


def aired(room, session, name="6pm News", **story_overrides):
    """An approved story in an approved, broadcast bulletin. Returns (story_id, bulletin)."""
    bulletin = make_bulletin(room, name=name)
    story_id, _ = approved_story(room, session, **story_overrides)
    room.as_(room.ep)
    assert put_items(room, bulletin["id"], 1, [{"story_id": story_id}]).status_code == 200
    assert revision_action(room, bulletin["id"], 1, "submit").status_code == 200
    assert revision_action(room, bulletin["id"], 1, "approve").status_code == 200
    broadcast = room.post(f"{B}/{bulletin['id']}/broadcast")
    assert broadcast.status_code == 200, broadcast.text
    return story_id, broadcast.json()
