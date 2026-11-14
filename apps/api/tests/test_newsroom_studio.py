"""NUST FM studio view: the one authoritative answer the studio screen polls. It always names the approved version
to read, with its script text, and says when a newer revision is waiting, without ever serving unapproved text."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from newsroom_helpers import (  # noqa: F401  (newsroom_client and room are fixtures)
    B,
    approved_story,
    live_bulletin,
    make_bulletin,
    make_staff,
    newsroom_client,
    put_items,
    revision_action,
    room,
    words,
)

pytestmark = pytest.mark.usefixtures("migrated_engine")


def studio(room, bulletin_id):
    return room.get(f"{B}/{bulletin_id}/studio")


def test_the_studio_route_does_not_exist_in_road_safety_mode(client):
    assert client.get(f"{B}/{uuid.uuid4()}/studio").status_code == 404


def test_anonymous_users_are_turned_away(room, session):
    bulletin = make_bulletin(room)
    room.client.cookies.clear()
    assert studio(room, bulletin["id"]).status_code == 401


@pytest.mark.parametrize("role", ["reporter", "analyst", "editor", "admin"])
def test_every_signed_in_newsroom_role_can_open_the_studio_view(room, session, role):
    """A reporter or the Executive Producer may be the one reading on air, so nobody signed in is locked out."""
    bulletin, _ = live_bulletin(room, session, stories=1)
    room.as_(make_staff(session, role))
    response = studio(room, bulletin["id"])
    assert response.status_code == 200 and response.json()["status"] == "approved"


def test_an_unknown_bulletin_is_a_404(room):
    make_bulletin(room)
    assert studio(room, uuid.uuid4()).json()["error"]["code"] == "BULLETIN_NOT_FOUND"


def test_a_bulletin_with_no_approved_version_says_so_and_serves_no_script(room, session):
    draft = make_bulletin(room, name="Not ready")
    story_id, _ = approved_story(room, session)
    room.as_(room.ep)
    put_items(room, draft["id"], 1, [{"story_id": story_id}])
    body = studio(room, draft["id"]).json()
    assert body["status"] == "not_approved" and body["version"] is None
    assert body["items"] == [] and body["total_seconds"] == 0 and body["approved_at"] is None and body["approved_by"] is None
    assert body["newer_revision_pending"] is False and body["name"] == "Not ready"
    # a submitted but unapproved revision is announced, not served
    revision_action(room, draft["id"], 1, "submit")
    waiting = studio(room, draft["id"]).json()
    assert waiting["status"] == "not_approved" and waiting["items"] == []
    assert waiting["newer_revision_pending"] is True and waiting["newer_revision_number"] == 1


def test_the_approved_version_is_served_with_its_script_text_in_order(room, session):
    bulletin = make_bulletin(room, name="6pm News", target_seconds=120)
    (s1, _), (s2, _) = approved_story(room, session, script_body="First story body."), approved_story(room, session, script_body=words(150))
    room.as_(room.ep)
    put_items(room, bulletin["id"], 1, [
        {"story_id": s2, "note": "Play clip 3 after the intro", "duration_override_seconds": 75},
        {"story_id": s1},
    ])
    revision_action(room, bulletin["id"], 1, "submit")
    revision_action(room, bulletin["id"], 1, "approve")

    response = studio(room, bulletin["id"])
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"  # the screen must never be answered from a cache
    view = response.json()
    assert view["status"] == "approved" and view["version"] == 1 and view["name"] == "6pm News" and view["target_seconds"] == 120
    assert view["approved_by"]["id"] == str(room.ep.id) and view["approved_at"]
    assert [i["position"] for i in view["items"]] == [1, 2]
    first, second = view["items"]
    assert first["body"] == " ".join(["word"] * 150) and first["note"] == "Play clip 3 after the intro"
    assert first["duration_seconds"] == 75 and first["duration_overridden"] is True
    assert second["body"] == "First story body." and second["headline"] == "Council approves budget"
    assert second["duration_seconds"] == 2 and second["duration_overridden"] is False  # 3 words at 150 wpm, rounded up
    assert view["total_seconds"] == 77
    assert view["newer_revision_pending"] is False and view["newer_revision_number"] is None and view["aired_at"] is None


def test_the_server_time_is_current(room, session):
    bulletin, _ = live_bulletin(room, session, stories=1)
    before = datetime.now(UTC) - timedelta(seconds=5)
    stamp = datetime.fromisoformat(studio(room, bulletin["id"]).json()["server_time"])
    assert before <= stamp <= datetime.now(UTC) + timedelta(seconds=5)


def test_a_newer_submitted_revision_is_reported_while_the_approved_one_stays_live(room, session):
    bulletin, ids = live_bulletin(room, session)
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[0]}])
    # a draft still being edited is not announced to the studio
    drafting = studio(room, bid).json()
    assert drafting["version"] == 1 and drafting["newer_revision_pending"] is False and len(drafting["items"]) == 2
    revision_action(room, bid, 2, "submit")
    waiting = studio(room, bid).json()
    assert waiting["version"] == 1 and waiting["status"] == "approved"  # still the approved one
    assert waiting["newer_revision_pending"] is True and waiting["newer_revision_number"] == 2
    assert len(waiting["items"]) == 2  # revision 1's running order, not revision 2's single story


def test_approving_the_newer_revision_moves_the_studio_to_it_and_no_stale_version_is_served(room, session):
    bulletin, ids = live_bulletin(room, session)
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[1]}])
    revision_action(room, bid, 2, "submit")
    assert studio(room, bid).json()["version"] == 1
    revision_action(room, bid, 2, "approve")
    now = studio(room, bid).json()
    assert now["version"] == 2 and now["newer_revision_pending"] is False and now["newer_revision_number"] is None
    assert len(now["items"]) == 1 and now["total_seconds"] == 30
    # the superseded version can no longer be obtained from the studio endpoint
    assert all(i["position"] == 1 for i in now["items"])


def test_a_rejected_newer_revision_leaves_the_studio_on_the_approved_one(room, session):
    bulletin, ids = live_bulletin(room, session)
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[0]}])
    revision_action(room, bid, 2, "submit")
    revision_action(room, bid, 2, "reject", {"comment": "Keep both"})
    view = studio(room, bid).json()
    assert view["version"] == 1 and view["newer_revision_pending"] is False and len(view["items"]) == 2


def test_the_studio_reads_the_approved_script_even_after_the_story_is_rewritten(room, session):
    bulletin, ids = live_bulletin(room, session, stories=1)
    before = studio(room, bulletin["id"]).json()["items"][0]["body"]
    room.as_(room.reporter)
    room.script(ids[0], body="A completely different, unapproved rewrite.", base=1)
    room.as_(room.analyst)
    assert studio(room, bulletin["id"]).json()["items"][0]["body"] == before  # the approved text, never the draft


def test_the_studio_shows_when_the_bulletin_went_to_air(room, session):
    bulletin, _ = live_bulletin(room, session, stories=1)
    room.post(f"{B}/{bulletin['id']}/broadcast")
    assert studio(room, bulletin["id"]).json()["aired_at"]


def test_the_studio_answer_is_small_and_carries_no_history(room, session):
    bulletin, _ = live_bulletin(room, session)
    view = studio(room, bulletin["id"]).json()
    assert set(view) == {
        "bulletin_id", "name", "scheduled_for", "target_seconds", "status", "version", "approved_at", "approved_by", "items",
        "total_seconds", "newer_revision_pending", "newer_revision_number", "aired_at", "server_time",
    }
    assert set(view["items"][0]) == {"position", "story_title", "headline", "body", "duration_seconds", "duration_overridden", "note"}
