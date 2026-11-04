"""Human editorial workflow: bulletin versions, decisions, authorisation and safeguards."""

import pytest
from geoalchemy2 import WKTElement
from sqlalchemy import select, text

import db_factories as f
from api_helpers import sign_in
from app.models import AuditEvent, Blackspot, BulletinVersion, EditorialReview, Incident

pytestmark = pytest.mark.usefixtures("migrated_engine")

V1 = "/api/v1"
CHECK, RESTRICT = "23514", "23001"


def bulletin_url(i):
    return f"{V1}/incidents/{i.id}/bulletins"


def review_url(i):
    return f"{V1}/incidents/{i.id}/reviews"


def draft(client, headers, incident, base=None, headline="Crash on A1", body="Two people died in a collision."):
    return client.post(bulletin_url(incident), json={"headline": headline, "body": body, "base_version": base}, headers=headers)


def decide(client, headers, incident, decision, version_id=None, notes=None):
    payload = {"decision": decision, "bulletin_version_id": version_id, "notes": notes}
    return client.post(review_url(incident), json=payload, headers=headers)


def code(response):
    return response.json()["error"]["code"]


# --- authorisation -------------------------------------------------------------------------------


def test_writes_need_an_editor_or_admin(client, session):
    incident = f.make_incident(session)
    session.commit()
    assert client.post(bulletin_url(incident), json={"headline": "h", "body": "b"}).status_code == 401

    for role in ("analyst", "contributor"):
        client.cookies.clear()
        _, headers = sign_in(client, session, role)
        assert draft(client, headers, incident).status_code == 403
        assert decide(client, headers, incident, "needs_changes", notes="x").status_code == 403
        assert client.post(f"{V1}/incidents/{incident.id}/location/confirm", json={"action": "mark_unresolved"}, headers=headers).status_code == 403
    assert session.scalar(select(BulletinVersion)) is None and session.scalar(select(EditorialReview)) is None


def test_analysts_can_read_the_editorial_record(client, session):
    editor, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    draft(client, headers, incident)
    client.cookies.clear()
    sign_in(client, session, "analyst")
    assert client.get(bulletin_url(incident)).json()["total"] == 1
    assert client.get(review_url(incident)).json()["total"] == 0
    assert client.get(f"{V1}/reviews/pending").status_code == 200


def test_the_reviewer_is_the_session_user_and_cannot_be_impersonated(client, session):
    other = f.make_user(session, "admin")
    editor, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    version = draft(client, headers, incident).json()

    forged = client.post(review_url(incident), headers=headers, json={
        "decision": "approved", "bulletin_version_id": version["id"], "reviewer_id": str(other.id)})
    assert forged.status_code == 422
    assert session.scalar(select(EditorialReview)) is None

    ok = decide(client, headers, incident, "approved", version["id"])
    assert ok.status_code == 201
    stored = session.scalar(select(EditorialReview))
    assert stored.reviewer_id == editor.id and ok.json()["review"]["reviewer_id"] == str(editor.id)
    assert ok.json()["review"]["reviewer_name"] == editor.display_name


def test_state_changing_editorial_calls_require_csrf(client, session):
    sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    assert client.post(bulletin_url(incident), json={"headline": "h", "body": "b"}).status_code == 403


# --- bulletin versions ------------------------------------------------------------------------------


def test_versions_are_appended_and_old_ones_stay_unchanged(client, session):
    editor, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()

    first = draft(client, headers, incident, None, "First headline", "First body.")
    assert first.status_code == 201 and first.json()["version_number"] == 1 and first.json()["created_by"] == str(editor.id)
    second = draft(client, headers, incident, 1, "Second headline", "Second body.")
    assert second.json()["version_number"] == 2

    listing = client.get(bulletin_url(incident)).json()
    assert [v["version_number"] for v in listing["items"]] == [2, 1]
    assert [v["is_latest"] for v in listing["items"]] == [True, False]
    assert listing["items"][1]["headline"] == "First headline" and listing["items"][1]["body"] == "First body."
    session.refresh(incident)
    assert incident.status == "under_review"


def test_concurrent_edits_conflict_instead_of_overwriting(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    assert draft(client, headers, incident, None).status_code == 201
    stale_first = draft(client, headers, incident, None)  # second editor still believes there is no draft
    assert stale_first.status_code == 409 and code(stale_first) == "BULLETIN_VERSION_CONFLICT"
    assert draft(client, headers, incident, 1).status_code == 201
    assert draft(client, headers, incident, 1).status_code == 409  # now behind by one
    assert len(session.scalars(select(BulletinVersion)).all()) == 2


def test_bulletin_validation_and_personal_data_guard(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    assert draft(client, headers, incident, headline="  ").status_code == 422
    leaked = draft(client, headers, incident, body="Call the driver on +263 77 123 4567 or a@b.co")
    assert leaked.status_code == 422 and code(leaked) == "BULLETIN_CONTAINS_PERSONAL_DATA"
    assert "4567" not in leaked.text and "a@b.co" not in leaked.text
    assert session.scalar(select(BulletinVersion)) is None


def test_closed_incidents_cannot_be_edited(client, session):
    _, headers = sign_in(client, session, "editor")
    rejected = f.make_incident(session, status="rejected")
    session.commit()
    response = draft(client, headers, rejected)
    assert response.status_code == 409 and code(response) == "INCIDENT_NOT_EDITABLE"
    assert client.post(f"{V1}/incidents/00000000-0000-0000-0000-000000000000/bulletins",
                       json={"headline": "h", "body": "b"}, headers=headers).status_code == 404


# --- decisions --------------------------------------------------------------------------------------------


def test_approval_applies_to_exactly_one_version(client, session):
    editor, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    v1 = draft(client, headers, incident).json()

    response = decide(client, headers, incident, "approved", v1["id"], notes="Verified with ZRP")
    assert response.status_code == 201
    body = response.json()
    assert body["review"]["version_number"] == 1 and body["review"]["notes"] == "Verified with ZRP"
    assert body["incident"]["status"] == "approved" and body["incident"]["review_state"] == "approved"
    session.refresh(incident)
    assert incident.status == "approved"
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "review.approved")).one()
    assert event.actor_user_id == editor.id and event.details["version"] == 1


def test_stale_wrong_and_missing_versions_are_refused(client, session):
    _, headers = sign_in(client, session, "editor")
    incident, other = f.make_incident(session), f.make_incident(session)
    session.commit()
    v1 = draft(client, headers, incident).json()
    draft(client, headers, incident, 1)
    foreign = draft(client, headers, other).json()

    stale = decide(client, headers, incident, "approved", v1["id"])
    assert stale.status_code == 409 and code(stale) == "STALE_BULLETIN_VERSION"
    mismatch = decide(client, headers, incident, "approved", foreign["id"])
    assert mismatch.status_code == 422 and code(mismatch) == "BULLETIN_VERSION_MISMATCH"
    missing = decide(client, headers, incident, "approved", "00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404 and code(missing) == "BULLETIN_VERSION_NOT_FOUND"
    assert decide(client, headers, incident, "approved").status_code == 422  # a version is required
    assert session.scalar(select(EditorialReview)) is None
    session.refresh(incident)
    assert incident.status == "under_review"


def test_revision_after_approval_reopens_the_incident_and_needs_new_approval(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    v1 = draft(client, headers, incident).json()
    assert decide(client, headers, incident, "approved", v1["id"]).status_code == 201

    v2 = draft(client, headers, incident, 1, "Corrected headline", "Corrected body.")
    assert v2.status_code == 201
    session.refresh(incident)
    assert incident.status == "under_review"
    assert client.get(f"{V1}/incidents/{incident.id}").json()["review_state"] == "pending_review"
    old = session.scalar(select(BulletinVersion).where(BulletinVersion.version_number == 1))
    assert old.headline == "Crash on A1"  # the approved text is untouched

    stale = decide(client, headers, incident, "approved", v1["id"])  # the old approval does not carry over
    assert stale.status_code == 409
    assert decide(client, headers, incident, "approved", v2.json()["id"]).status_code == 201
    history = client.get(review_url(incident)).json()
    assert history["total"] == 2 and [r["version_number"] for r in history["items"]] == [2, 1]


def test_rejection_and_change_requests_need_notes(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    draft(client, headers, incident)
    for decision in ("rejected", "needs_changes"):
        assert decide(client, headers, incident, decision).status_code == 422
        assert decide(client, headers, incident, decision, notes="   ").status_code == 422

    changes = decide(client, headers, incident, "needs_changes", notes="Confirm the location first")
    assert changes.status_code == 201 and changes.json()["incident"]["review_state"] == "needs_changes"
    assert changes.json()["review"]["version_number"] == 1  # defaulted to the current text
    session.refresh(incident)
    assert incident.status == "under_review"

    rejected = decide(client, headers, incident, "rejected", notes="Not a road incident")
    assert rejected.json()["incident"]["status"] == "rejected"
    again = decide(client, headers, incident, "needs_changes", notes="late")
    assert again.status_code == 409 and code(again) == "INCIDENT_NOT_REVIEWABLE"


def test_decisions_on_unlocated_incidents_are_allowed_and_recorded(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session, location_status="unresolved")
    session.commit()
    v1 = draft(client, headers, incident).json()
    assert decide(client, headers, incident, "approved", v1["id"]).status_code == 201
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "review.approved")).one()
    assert event.details["location_status"] == "unresolved"


def test_pending_queue_is_ordered_by_priority_then_age(client, session):
    sign_in(client, session, "editor")
    low = f.make_incident(session, review_priority="low")
    urgent = f.make_incident(session, review_priority="urgent")
    high_old = f.make_incident(session, review_priority="high")
    high_new = f.make_incident(session, review_priority="high")
    done = f.make_incident(session, status="rejected")
    session.execute(text("UPDATE incidents SET created_at = created_at - interval '1 day' WHERE id = :i"), {"i": high_old.id})
    session.commit()

    body = client.get(f"{V1}/reviews/pending").json()
    assert [i["id"] for i in body["items"]] == [str(urgent.id), str(high_old.id), str(high_new.id), str(low.id)]
    assert str(done.id) not in [i["id"] for i in body["items"]]


# --- database safeguards remain the backstop ---------------------------------------------------------------------


def test_database_refuses_what_the_api_would_never_do(session, db_error):
    editor, analyst = f.make_user(session, "editor"), f.make_user(session, "analyst")
    incident = f.make_incident(session)
    v1 = f.make_bulletin(session, incident, editor, 1)
    v2 = f.make_bulletin(session, incident, editor, 2)

    with db_error(session, CHECK):  # approving a superseded version
        f.make_review(session, incident, v1, editor)
    with db_error(session, CHECK):  # an analyst is not a reviewer
        f.make_review(session, incident, v2, analyst)
    with db_error(session, CHECK):  # no status jump to approved without a review
        session.execute(text("UPDATE incidents SET status = 'approved' WHERE id = :i"), {"i": incident.id})
    approval = f.make_review(session, incident, v2, editor)
    with db_error(session, RESTRICT):  # history is append-only
        session.execute(text("UPDATE editorial_reviews SET decision = 'rejected' WHERE id = :i"), {"i": approval.id})
    with db_error(session, RESTRICT):
        session.execute(text("UPDATE bulletin_versions SET body = 'edited' WHERE id = :i"), {"i": v1.id})
    session.add(AuditEvent(action="test.event", entity_type="incident"))
    session.flush()
    with db_error(session, RESTRICT):
        session.execute(text("DELETE FROM audit_events"))
    f.make_review(session, incident, v1, editor, "needs_changes")  # only approvals must name the latest version


# --- location confirmation --------------------------------------------------------------------------------------------


def confirm(client, headers, incident, **body):
    return client.post(f"{V1}/incidents/{incident.id}/location/confirm", json=body, headers=headers)


def test_editor_accepts_a_proposed_location(client, session):
    editor, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session, location_status="resolved", location_precision_m=40,
                               geom=WKTElement("POINT(31.05 -17.83)", srid=4326), location_method="google_geocoding")
    session.commit()
    response = confirm(client, headers, incident, action="accept_proposed", note="Matches the article")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "editor_confirmed" and body["confirmed_by_editor"] is True
    assert body["confirmed_by"] == str(editor.id) and body["note"] == "Matches the article"
    assert body["coordinates"]["longitude"] == pytest.approx(31.05)
    event = session.scalars(select(AuditEvent).where(AuditEvent.action == "incident.location_confirmed")).one()
    assert event.actor_user_id == editor.id


def test_cannot_accept_a_proposal_that_does_not_exist(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session, location_status="ambiguous")
    session.commit()
    response = confirm(client, headers, incident, action="accept_proposed")
    assert response.status_code == 409 and code(response) == "NO_PROPOSED_LOCATION"


def test_editor_selects_a_candidate_and_blackspots_are_rematched(client, session):
    _, headers = sign_in(client, session, "editor")
    candidates = [
        {"label": "Mbudzi, Harare", "latitude": -17.86, "longitude": 31.02, "precision_meters": 120, "match_type": "approx", "source": "Test"},
        {"label": "Mbudzi, Mutare", "latitude": -18.97, "longitude": 32.67, "precision_meters": None, "match_type": "approx", "source": "Test"},
    ]
    incident = f.make_incident(session, location_status="ambiguous", location_candidates=candidates)
    session.add(Blackspot(name="Mbudzi roundabout", geom=WKTElement("POINT(31.0205 -17.8603)", srid=4326),
                          source_name="Test dataset", risk_level="critical"))
    session.commit()

    assert confirm(client, headers, incident, action="select_candidate", candidate_index=5).status_code == 422
    assert confirm(client, headers, incident, action="select_candidate").status_code == 422
    chosen = confirm(client, headers, incident, action="select_candidate", candidate_index=0)
    assert chosen.status_code == 200 and chosen.json()["status"] == "editor_confirmed"
    assert chosen.json()["precision_meters"] == 120 and chosen.json()["resolution_method"] == "editor_selected_candidate"
    matches = client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()
    assert matches["status"] == "matched" and matches["geographic_risk_score"] > 0.9


def test_editor_can_supply_coordinates_but_only_inside_zimbabwe(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.commit()
    outside = confirm(client, headers, incident, action="set_coordinates", latitude=51.5, longitude=-0.12)
    assert outside.status_code == 422 and code(outside) == "OUTSIDE_ZIMBABWE"
    assert confirm(client, headers, incident, action="set_coordinates", latitude=-17.83).status_code == 422
    ok = confirm(client, headers, incident, action="set_coordinates", latitude=-17.83, longitude=31.05, precision_meters=25)
    assert ok.status_code == 200 and ok.json()["source"] == "Editor" and ok.json()["precision_meters"] == 25


def test_marking_unresolved_removes_the_point_and_matches(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session)
    session.add(Blackspot(name="Spot", geom=WKTElement("POINT(31.05 -17.83)", srid=4326), source_name="Test", risk_level="high"))
    session.commit()
    confirm(client, headers, incident, action="set_coordinates", latitude=-17.83, longitude=31.05)
    assert client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()["status"] == "matched"

    cleared = confirm(client, headers, incident, action="mark_unresolved", note="Editor could not verify")
    assert cleared.json()["status"] == "unresolved" and cleared.json()["coordinates"] is None
    assert cleared.json()["confirmed_by_editor"] is False
    after = client.get(f"{V1}/incidents/{incident.id}/blackspot-matches").json()
    assert after["status"] == "location_unknown" and after["matches"] == []
    session.refresh(incident)
    assert incident.geom is None and incident.geographic_risk_score is None


def test_decided_incidents_keep_their_location(client, session):
    _, headers = sign_in(client, session, "editor")
    incident = f.make_incident(session, status="rejected")
    session.commit()
    response = confirm(client, headers, incident, action="mark_unresolved")
    assert response.status_code == 409 and code(response) == "INCIDENT_NOT_EDITABLE"
    assert session.get(Incident, incident.id).location_confirmed_by is None
