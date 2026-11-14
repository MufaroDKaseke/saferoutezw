"""NUST FM newsroom API: browsing, search and filters, the review flag, retry, metrics, roles and mode gating."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import db_factories as f
from api_helpers import sign_in
from app.models import AuditEvent, ExtractionRun, IngestionRun, SourceItem
from newsroom_helpers import classification, make_article, newsroom_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("migrated_engine")

N = "/api/v1/newsroom"


def ids(response):
    return {i["id"] for i in response.json()["items"]}


def named_source(session, name):
    source = f.make_source(session)
    source.name = name
    session.commit()
    return source


# ---- access ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/summary", "/categories", "/articles"])
def test_anonymous_users_are_turned_away(newsroom_client, path):
    assert newsroom_client.get(N + path).status_code == 401


def test_analysts_can_read_but_not_change_anything(newsroom_client, session):
    article = make_article(session)
    _, headers = sign_in(newsroom_client, session, "analyst")
    assert newsroom_client.get(f"{N}/articles").status_code == 200
    assert newsroom_client.get(f"{N}/articles/{article.id}").status_code == 200
    review = newsroom_client.patch(f"{N}/articles/{article.id}/review", json={"status": "used"}, headers=headers)
    assert review.status_code == 403
    assert newsroom_client.post(f"{N}/articles/{article.id}/retry", headers=headers).status_code == 403


def test_the_thirteen_categories_are_listed(newsroom_client, session):
    sign_in(newsroom_client, session, "analyst")
    body = newsroom_client.get(f"{N}/categories").json()
    assert len(body) == 13
    assert {"value": "politics_governance", "label": "Politics & Governance"} in body
    assert body[-1] == {"value": "other", "label": "Other / Unclassified"}


# ---- list, search and filters --------------------------------------------------------------------------


def test_articles_show_headline_publisher_link_summary_and_category(newsroom_client, session):
    herald = named_source(session, "The Herald")
    article = make_article(
        session, herald, title_redacted="Budget presented", canonical_url="https://herald.test/budget",
        reply=classification(summary="Parliament debated the budget.", secondary_category="business_economy"),
    )
    sign_in(newsroom_client, session, "analyst")
    item = newsroom_client.get(f"{N}/articles").json()["items"][0]
    assert item["id"] == str(article.id) and item["publisher"] == "The Herald"
    assert item["headline"] == "Budget presented" and item["source_url"] == "https://herald.test/budget"
    assert item["state"] == "classified" and item["category"] == "politics_governance"
    assert item["secondary_category"] == "business_economy" and item["summary"] == "Parliament debated the budget."
    assert item["review"]["status"] == "new" and item["classification_basis"] == "full_text"


def test_search_covers_headline_excerpt_article_text_and_ai_summary(newsroom_client, session):
    a = make_article(session, title_redacted="Zebra in the headline")
    b = make_article(session, excerpt_redacted="A giraffe in the excerpt")
    c = make_article(session, article_text_redacted="An okapi in the body text of the article")
    d = make_article(session, reply=classification(summary="A pangolin only in the AI summary"))
    make_article(session, title_redacted="Nothing relevant")
    sign_in(newsroom_client, session, "analyst")
    for term, expected in (("zebra", a), ("giraffe", b), ("okapi", c), ("pangolin", d)):
        assert ids(newsroom_client.get(f"{N}/articles", params={"q": term})) == {str(expected.id)}, term
    assert newsroom_client.get(f"{N}/articles", params={"q": "100%_"}).json()["total"] == 0  # wildcards are escaped


def test_filters_by_publisher_category_state_review_and_dates(newsroom_client, session):
    herald, newsday = named_source(session, "The Herald"), named_source(session, "NewsDay")
    now = datetime.now(UTC)
    politics = make_article(session, herald, reply=classification(primary_category="politics_governance"),
                            published_at=now - timedelta(days=1))
    sport = make_article(session, newsday, reply=classification(primary_category="sports", secondary_category="entertainment_culture"),
                         published_at=now - timedelta(days=10))
    pending = make_article(session, herald, status="fetched")
    failed = make_article(session, newsday, status="failed")
    skipped = make_article(session, herald, status="filtered")
    sign_in(newsroom_client, session, "analyst")
    get = lambda **p: ids(newsroom_client.get(f"{N}/articles", params=p))  # noqa: E731

    assert get(publisher_id=str(newsday.id)) == {str(sport.id), str(failed.id)}
    assert get(category="sports") == {str(sport.id)}
    assert get(category="entertainment_culture") == {str(sport.id)}  # secondary categories match too
    assert get(state="classified") == {str(politics.id), str(sport.id)}
    assert get(state="pending") == {str(pending.id)}
    assert get(state="failed") == {str(failed.id)}
    assert get(state="skipped") == {str(skipped.id)}
    assert get(published_from=(now - timedelta(days=3)).isoformat(), category="politics_governance") == {str(politics.id)}
    assert get(published_to=(now - timedelta(days=5)).isoformat()) == {str(sport.id)}
    assert get(collected_from=(now + timedelta(hours=1)).isoformat()) == set()
    assert get(review_status="new") >= {str(politics.id), str(sport.id)}


def test_unknown_categories_and_oversized_pages_are_rejected(newsroom_client, session):
    sign_in(newsroom_client, session, "analyst")
    assert newsroom_client.get(f"{N}/articles", params={"category": "road_incident"}).status_code == 422
    assert newsroom_client.get(f"{N}/articles", params={"page_size": 101}).status_code == 422
    assert newsroom_client.get(f"{N}/articles", params={"state": "bogus"}).status_code == 422


def test_paging_and_sorting_are_stable(newsroom_client, session):
    now = datetime.now(UTC)
    made = [make_article(session, published_at=now - timedelta(hours=i)) for i in range(5)]
    sign_in(newsroom_client, session, "analyst")
    page1 = newsroom_client.get(f"{N}/articles", params={"page_size": 2, "sort": "published_at", "order": "desc"}).json()
    page2 = newsroom_client.get(f"{N}/articles", params={"page_size": 2, "page": 2, "sort": "published_at", "order": "desc"}).json()
    assert page1["total"] == 5 and [i["id"] for i in page1["items"]] == [str(made[0].id), str(made[1].id)]
    assert [i["id"] for i in page2["items"]] == [str(made[2].id), str(made[3].id)]


# ---- detail --------------------------------------------------------------------------------------------


def test_detail_has_the_summary_entities_text_and_provenance(newsroom_client, session):
    article = make_article(
        session, excerpt_redacted="Feed excerpt", article_text_redacted="Full article text",
        reply=classification(topics=["budget"], organisations=["Treasury"], places=["Harare"], needs_editorial_attention=True,
                             attention_reason="Allegation against a named official"),
    )
    sign_in(newsroom_client, session, "analyst")
    body = newsroom_client.get(f"{N}/articles/{article.id}").json()
    assert (body["excerpt"], body["article_text"]) == ("Feed excerpt", "Full article text")
    assert (body["topics"], body["organisations"], body["places"]) == (["budget"], ["Treasury"], ["Harare"])
    assert body["needs_editorial_attention"] is True and body["attention_reason"] == "Allegation against a named official"
    assert body["classification_confidence"] == 0.9 and body["model"] == "fake-newsroom-model-1"
    assert body["prompt_version"] == "newsroom-v1" and body["classified_at"]


def test_a_missing_article_is_a_404(newsroom_client, session):
    sign_in(newsroom_client, session, "analyst")
    assert newsroom_client.get(f"{N}/articles/00000000-0000-0000-0000-000000000000").status_code == 404


# ---- review flag -----------------------------------------------------------------------------------------


def test_editors_flag_articles_and_it_is_audited(newsroom_client, session):
    article = make_article(session)
    user, headers = sign_in(newsroom_client, session, "editor")
    response = newsroom_client.patch(f"{N}/articles/{article.id}/review", json={"status": "used", "note": "Aired at 6pm"}, headers=headers)
    assert response.status_code == 200
    review = response.json()["review"]
    assert (review["status"], review["note"], review["by"]) == ("used", "Aired at 6pm", user.display_name)
    session.expire_all()
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "newsroom.article_reviewed")).one()
    assert event.actor_user_id == user.id and event.details == {"status": "used", "previous": "new"}
    assert "Aired at 6pm" not in str(event.details)  # the note stays on the article, not in the audit log
    assert ids(newsroom_client.get(f"{N}/articles", params={"review_status": "used"})) == {str(article.id)}
    assert ids(newsroom_client.get(f"{N}/articles", params={"review_status": "new"})) == set()


def test_the_review_flag_needs_a_known_status_and_the_csrf_token(newsroom_client, session):
    article = make_article(session)
    _, headers = sign_in(newsroom_client, session, "editor")
    assert newsroom_client.patch(f"{N}/articles/{article.id}/review", json={"status": "published"}, headers=headers).status_code == 422
    assert newsroom_client.patch(f"{N}/articles/{article.id}/review", json={"status": "used"}).status_code == 403


def test_the_review_flag_never_touches_the_classification(newsroom_client, session):
    article = make_article(session)
    _, headers = sign_in(newsroom_client, session, "admin")
    before = dict(article.source_metadata["classification"])
    newsroom_client.patch(f"{N}/articles/{article.id}/review", json={"status": "dismissed"}, headers=headers)
    session.expire_all()
    assert article.source_metadata["classification"] == before and article.processing_status == "processed"


# ---- retry -----------------------------------------------------------------------------------------------


def test_a_failed_article_can_be_queued_again_and_keeps_its_history(newsroom_client, session):
    article = make_article(session, status="failed", article_text_redacted="Body")
    session.add(ExtractionRun(source_item_id=article.id, model_name="m", status="failed", error_message="boom"))
    session.commit()
    _, headers = sign_in(newsroom_client, session, "editor")
    response = newsroom_client.post(f"{N}/articles/{article.id}/retry", headers=headers)
    assert response.status_code == 200 and response.json()["state"] == "pending"
    session.expire_all()
    assert article.processing_status == "fetched" and "extraction_retry_epoch" in article.source_metadata
    assert session.scalars(select(ExtractionRun)).one().error_message == "boom"  # history kept
    assert session.scalars(select(AuditEvent).where(AuditEvent.action == "newsroom.article_retry")).one()


def test_a_fetch_failed_article_goes_back_to_the_start_of_the_queue(newsroom_client, session):
    article = make_article(session, status="fetch_failed", fetch_error="HTTP 403", fetch_status="failed")
    _, headers = sign_in(newsroom_client, session, "editor")
    assert newsroom_client.post(f"{N}/articles/{article.id}/retry", headers=headers).status_code == 200
    session.expire_all()
    assert (article.processing_status, article.fetch_error, article.fetch_status) == ("screened", None, None)


def test_only_failed_articles_can_be_retried(newsroom_client, session):
    article = make_article(session)
    _, headers = sign_in(newsroom_client, session, "editor")
    assert newsroom_client.post(f"{N}/articles/{article.id}/retry", headers=headers).status_code == 409


# ---- summary metrics ---------------------------------------------------------------------------------------


def test_summary_reports_the_newsroom_numbers(newsroom_client, session):
    now = datetime.now(UTC)
    herald, newsday = named_source(session, "The Herald"), named_source(session, "NewsDay")
    make_article(session, herald, reply=classification(primary_category="politics_governance"))
    old = make_article(session, herald, reply=classification(primary_category="sports"))
    old.received_at = now - timedelta(days=3)
    old.source_metadata = {**old.source_metadata, "classification": {**old.source_metadata["classification"], "at": (now - timedelta(days=3)).isoformat()}}
    make_article(session, newsday, status="pending")
    make_article(session, newsday, status="fetched")
    make_article(session, newsday, status="failed")
    make_article(session, newsday, status="fetch_failed")
    session.add(ExtractionRun(source_item_id=old.id, model_name="m", prompt_version="newsroom-v1", status="succeeded",
                              input_tokens=2_000_000, output_tokens=1_000_000, completed_at=now))
    session.add(ExtractionRun(source_item_id=old.id, model_name="m", prompt_version="transport-intel-v1", status="succeeded",
                              input_tokens=999, output_tokens=999, completed_at=now))  # a road-mode run is not counted
    session.commit()
    sign_in(newsroom_client, session, "analyst")
    body = newsroom_client.get(f"{N}/summary").json()
    assert body["total_articles"] == 6
    assert body["collected_today"] == 5 and body["classified_today"] == 1
    assert body["pending_classification"] == 2 and body["failures"] == 2
    assert body["usage_today"] == {"input_tokens": 2_000_000, "output_tokens": 1_000_000, "estimated_cost_usd": 0.9}  # 2*0.15 + 1*0.60
    counts = {c["key"]: c["count"] for c in body["by_category"]}
    assert counts["politics_governance"] == 1 and counts["sports"] == 1 and len(counts) == 13
    publishers = {p["name"]: (p["articles"], p["classified"]) for p in body["publishers"]}
    assert publishers == {"The Herald": (2, 2), "NewsDay": (4, 0)}


def test_feed_health_counts_recent_successful_polls_only(newsroom_client, session):
    now = datetime.now(UTC)
    healthy, stale, never, off = (named_source(session, n) for n in ("Healthy", "Stale", "Never", "Off"))
    off.enabled = False
    session.add_all([
        IngestionRun(source_id=healthy.id, started_at=now - timedelta(minutes=2), completed_at=now - timedelta(minutes=2), status="succeeded"),
        IngestionRun(source_id=stale.id, started_at=now - timedelta(days=2), completed_at=now - timedelta(days=2), status="succeeded"),
        IngestionRun(source_id=never.id, started_at=now - timedelta(minutes=1), completed_at=now - timedelta(minutes=1), status="failed",
                     error_message="timeout"),
    ])
    session.commit()
    sign_in(newsroom_client, session, "analyst")
    assert newsroom_client.get(f"{N}/summary").json()["feeds"] == {"enabled": 3, "healthy": 1, "unhealthy": 2, "disabled": 1}


def test_the_cost_estimate_is_absent_without_configured_prices(session):
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.core.database import get_db
    from app.main import create_app
    from public_helpers import make_settings

    settings = make_settings(app_mode="nust_newsroom")
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        sign_in(client, session, "analyst")
        assert client.get(f"{N}/summary").json()["usage_today"]["estimated_cost_usd"] is None


# ---- the mode switch ---------------------------------------------------------------------------------------


ROAD_PATHS = [
    "/api/v1/incidents", "/api/v1/blackspots", "/api/v1/blackspots/map", "/api/v1/alerts", "/api/v1/reviews/counts",
    "/api/v1/dashboard/summary", "/api/v1/news", "/api/v1/intelligence", "/api/v1/summaries",
    "/api/v1/public/summary", "/api/v1/public/alerts", "/api/v1/public/map", "/api/v1/public/subscriptions/options",
    "/api/v1/public/transport/news",
]


@pytest.mark.parametrize("path", ROAD_PATHS)
def test_road_safety_endpoints_do_not_exist_in_newsroom_mode(newsroom_client, session, path):
    sign_in(newsroom_client, session, "admin")  # even an administrator cannot reach them
    assert newsroom_client.get(path).status_code == 404


def test_the_whatsapp_webhook_does_not_exist_in_newsroom_mode(newsroom_client):
    assert newsroom_client.post("/api/v1/webhooks/whatsapp", content=b"{}").status_code == 404
    assert newsroom_client.get("/api/v1/webhooks/whatsapp").status_code == 404


def test_shared_features_still_work_in_newsroom_mode(newsroom_client, session):
    _, _ = sign_in(newsroom_client, session, "admin")
    assert newsroom_client.get("/health").status_code == 200
    assert newsroom_client.get("/api/v1/sources").status_code == 200
    assert newsroom_client.get("/api/v1/processing/runs").status_code == 200
    assert newsroom_client.get("/api/v1/admin/users").status_code == 200
    assert newsroom_client.get("/api/v1/auth/me").status_code == 200


def test_the_published_api_description_matches_the_mode(newsroom_client):
    paths = set(newsroom_client.get("/openapi.json").json()["paths"])
    assert f"{N}/articles" in paths and "/api/v1/incidents" not in paths and "/api/v1/public/alerts" not in paths
    assert not any(p.startswith("/api/v1/public") or p.startswith("/api/v1/webhooks") for p in paths)


def test_newsroom_endpoints_do_not_exist_in_road_safety_mode(client, session):
    sign_in(client, session, "admin")
    assert client.get(f"{N}/summary").status_code == 404
    assert client.get(f"{N}/articles").status_code == 404
    assert client.get("/api/v1/incidents").status_code == 200  # the original product is intact
    assert client.get("/api/v1/news").status_code == 200
