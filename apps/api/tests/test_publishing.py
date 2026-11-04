"""Explicit publication: approval is necessary but never sufficient."""

import pytest
from sqlalchemy import select

import db_factories as f
from api_helpers import sign_in
from app.models import AuditEvent, Incident, PublicAlert
from public_helpers import configure  # noqa: F401

pytestmark = pytest.mark.usefixtures("migrated_engine")

V1 = "/api/v1"


def code(response):
    return response.json()["error"]["code"]


def approved_incident(client, session, headers, headline="[SYNTHETIC] Crash near Marondera"):
    incident = f.make_incident(session, status="under_review", location_text="Marondera, Mashonaland East")
    session.commit()
    r = client.post(
        f"{V1}/incidents/{incident.id}/bulletins",
        json={"headline": headline, "body": "[SYNTHETIC] A crash was reported.", "base_version": None},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    version_id = r.json()["id"]
    r = client.post(
        f"{V1}/incidents/{incident.id}/reviews",
        json={"decision": "approved", "bulletin_version_id": version_id}, headers=headers,
    )
    assert r.status_code == 201, r.text
    return incident, version_id


def publish(client, headers, incident, version_id, **extra):
    return client.post(
        f"{V1}/incidents/{incident.id}/publish", json={"bulletin_version_id": version_id, **extra}, headers=headers
    )


def test_approval_does_not_publish(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, _ = approved_incident(client, session, headers)
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0
    assert session.scalar(select(PublicAlert).where(PublicAlert.incident_id == incident.id)) is None


def test_only_authorised_users_can_publish(client, session, configure):
    _, editor_headers = sign_in(client, session, "editor")
    incident, version_id = approved_incident(client, session, editor_headers)
    body = {"bulletin_version_id": version_id}
    client.cookies.clear()
    assert client.post(f"{V1}/incidents/{incident.id}/publish", json=body).status_code == 401
    for role in ("analyst", "contributor"):
        client.cookies.clear()
        _, headers = sign_in(client, session, role)
        assert publish(client, headers, incident, version_id).status_code == 403
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0


def test_publish_makes_the_exact_version_public_and_audits_it(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, version_id = approved_incident(client, session, headers)
    r = publish(client, headers, incident, version_id, province="mashonaland east", road_name="A3 Harare-Mutare")
    assert r.status_code == 200 and r.json()["status"] == "published"
    listing = client.get(f"{V1}/public/alerts").json()
    assert listing["total"] == 1 and listing["items"][0]["province"] == "Mashonaland East"
    assert session.get(Incident, incident.id).status == "published"
    actions = set(session.scalars(select(AuditEvent.action)).all())
    assert "alert.published" in actions
    assert publish(client, headers, incident, version_id).status_code == 409  # already published


def test_unapproved_incidents_cannot_be_published(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session, status="under_review")
    session.commit()
    r = client.post(
        f"{V1}/incidents/{incident.id}/bulletins",
        json={"headline": "h", "body": "b", "base_version": None}, headers=headers,
    )
    response = publish(client, headers, incident, r.json()["id"])
    assert response.status_code == 409 and code(response) == "INCIDENT_NOT_APPROVED"


def test_stale_versions_cannot_be_published(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, v1 = approved_incident(client, session, headers)
    # A revision reopens the incident; the old approval no longer covers the new text.
    r2 = client.post(
        f"{V1}/incidents/{incident.id}/bulletins",
        json={"headline": "Revised", "body": "[SYNTHETIC] Revised text.", "base_version": 1}, headers=headers,
    )
    v2 = r2.json()["id"]
    assert code(publish(client, headers, incident, v1)) == "INCIDENT_NOT_APPROVED"
    client.post(
        f"{V1}/incidents/{incident.id}/reviews",
        json={"decision": "approved", "bulletin_version_id": v2}, headers=headers,
    )
    stale = publish(client, headers, incident, v1)
    assert stale.status_code == 409 and code(stale) == "STALE_BULLETIN_VERSION"
    assert publish(client, headers, incident, v2).status_code == 200


def test_request_cannot_choose_approval_state(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, version_id = approved_incident(client, session, headers)
    r = publish(client, headers, incident, version_id, status="published", approval_review_id="x")
    assert r.status_code == 422


def test_unpublish_removes_public_visibility_and_keeps_approval(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, version_id = approved_incident(client, session, headers)
    publish(client, headers, incident, version_id)
    alert_id = client.get(f"{V1}/public/alerts").json()["items"][0]["id"]
    r = client.post(f"{V1}/incidents/{incident.id}/unpublish", json={"reason": "Road reopened"}, headers=headers)
    assert r.status_code == 200 and r.json()["status"] == "withdrawn"
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0
    assert client.get(f"{V1}/public/alerts/{alert_id}").status_code == 404
    assert session.get(Incident, incident.id).status == "approved"
    assert "alert.unpublished" in set(session.scalars(select(AuditEvent.action)).all())
    assert client.post(f"{V1}/incidents/{incident.id}/unpublish", json={}, headers=headers).status_code == 409
    # Republishing the same approved version is an explicit, separate act.
    assert publish(client, headers, incident, version_id).status_code == 200
    assert client.get(f"{V1}/public/alerts").json()["total"] == 1


# --- newsroom alerts: approved incidents flow in automatically, publishing is one explicit click ----


def test_approved_incident_appears_in_newsroom_alerts_but_not_public(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, version_id = approved_incident(client, session, headers)
    listing = client.get(f"{V1}/alerts", headers=headers).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["id"] == str(incident.id) and item["publication_state"] == "approved_not_published"
    assert item["status"] == "ready" and item["channels"] == [] and item["bulletin_version_id"] == version_id
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0  # approval alone is not publication


def test_one_click_publish_makes_it_public_and_unpublish_withdraws_it(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    incident, _ = approved_incident(client, session, headers)
    r = client.post(f"{V1}/alerts/{incident.id}/publish", json={}, headers=headers)
    assert r.status_code == 200 and r.json()["publication_state"] == "published"
    assert r.json()["channels"][0]["channel"] == "web"
    assert client.get(f"{V1}/public/alerts").json()["total"] == 1
    assert client.post(f"{V1}/alerts/{incident.id}/publish", json={}, headers=headers).status_code == 409
    state = client.get(f"{V1}/alerts?state=published", headers=headers).json()
    assert state["total"] == 1
    r = client.post(f"{V1}/alerts/{incident.id}/unpublish", json={"reason": "test"}, headers=headers)
    assert r.status_code == 200 and r.json()["publication_state"] == "withdrawn"
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0


def test_only_editors_can_publish_from_the_alerts_page(client, session, configure):
    _, editor_headers = sign_in(client, session, "editor")
    incident, _ = approved_incident(client, session, editor_headers)
    client.cookies.clear()
    assert client.post(f"{V1}/alerts/{incident.id}/publish", json={}).status_code == 401
    client.cookies.clear()
    _, analyst = sign_in(client, session, "analyst")
    assert client.get(f"{V1}/alerts", headers=analyst).status_code == 200  # may read
    assert client.post(f"{V1}/alerts/{incident.id}/publish", json={}, headers=analyst).status_code == 403
    assert client.get(f"{V1}/public/alerts").json()["total"] == 0


def test_unapproved_incidents_are_not_listed_as_alerts(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    f.make_incident(session, status="candidate")
    session.commit()
    assert client.get(f"{V1}/alerts", headers=headers).json()["total"] == 0


def test_alert_state_filters_the_ui_uses_are_accepted(client, session, configure):
    _, headers = sign_in(client, session, "editor")
    approved_incident(client, session, headers)
    for state in ("delivery_failed", "publication_pending"):
        r = client.get(f"{V1}/alerts", params={"state": state, "page_size": 1}, headers=headers)
        assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get(f"{V1}/alerts", params={"state": "nonsense"}, headers=headers).status_code == 422
