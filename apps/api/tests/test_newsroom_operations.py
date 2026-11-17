"""Newsroom Operations are admin-only; publishers and personal accounts remain available."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

import db_factories as f
from api_helpers import PASSWORD, sign_in
from app.models import IngestionRun
from newsroom_helpers import newsroom_client  # noqa: F401 (fixture)

pytestmark = pytest.mark.usefixtures("migrated_engine")


@pytest.mark.parametrize("role", ["editor", "reporter", "analyst", "contributor", "service"])
def test_non_admins_cannot_read_operational_endpoints(newsroom_client, session, role):
    source = f.make_source(session)
    session.commit()
    sign_in(newsroom_client, session, role)
    for path in (
        "/sources", f"/sources/{source.id}", f"/sources/{source.id}/runs",
        "/processing/backlog", "/processing/runs", f"/processing/runs/{uuid.uuid4()}",
    ):
        response = newsroom_client.get("/api/v1" + path)
        assert response.status_code == 403, (role, path, response.text)


def test_admins_can_load_processing_sources_and_run_details(newsroom_client, session):
    source = f.make_source(session)
    now = datetime.now(UTC)
    run = IngestionRun(source_id=source.id, status="succeeded", started_at=now, completed_at=now)
    session.add(run)
    session.commit()
    sign_in(newsroom_client, session, "admin")
    for path in (
        "/sources", f"/sources/{source.id}", f"/sources/{source.id}/runs",
        "/processing/backlog", "/processing/runs", f"/processing/runs/{run.id}",
    ):
        response = newsroom_client.get("/api/v1" + path)
        assert response.status_code == 200, (path, response.text)


def test_processing_backlog_counts_waiting_and_failed_articles_without_a_road_dashboard(newsroom_client, session):
    sign_in(newsroom_client, session, "admin")
    empty = newsroom_client.get("/api/v1/processing/backlog")
    assert empty.json() == {"awaiting_screening": 0, "awaiting_full_text": 0, "awaiting_extraction": 0, "failed_needing_attention": 0}
    source = f.make_source(session)
    old = datetime.now(UTC) - timedelta(days=30)
    for state in ("pending", "pending", "screened", "fetched", "fetched", "fetched", "failed", "fetch_failed", "fetch_failed", "processed", "filtered", "discarded", "processing"):
        f.make_source_item(session, source, processing_status=state, received_at=old)
    session.commit()
    response = newsroom_client.get("/api/v1/processing/backlog")
    assert response.status_code == 200
    assert response.json() == {"awaiting_screening": 2, "awaiting_full_text": 1, "awaiting_extraction": 3, "failed_needing_attention": 3}
    assert newsroom_client.get("/api/v1/dashboard/summary").status_code == 404


@pytest.mark.parametrize("role", ["admin", "editor", "reporter", "analyst"])
def test_all_newsroom_roles_can_get_publisher_labels_without_source_configuration(newsroom_client, session, role):
    one, two = f.make_source(session), f.make_source(session)
    one.name, two.name, two.enabled = "Alpha News", "Zed News", False
    session.commit()
    sign_in(newsroom_client, session, role)
    response = newsroom_client.get("/api/v1/newsroom/publishers")
    assert response.status_code == 200
    assert response.json() == [{"id": str(one.id), "name": "Alpha News"}, {"id": str(two.id), "name": "Zed News"}]


def test_producer_keeps_personal_account_and_password_access(newsroom_client, session):
    _, headers = sign_in(newsroom_client, session, "editor")
    assert newsroom_client.get("/api/v1/auth/me").status_code == 200
    assert newsroom_client.get("/api/v1/sources").status_code == 403
    response = newsroom_client.post("/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "a new producer passphrase"}, headers=headers)
    assert response.status_code == 204
