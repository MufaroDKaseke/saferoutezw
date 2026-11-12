"""NUST FM radio bulletins: building a timed running order, submitting it, approving a revision, the atomic swap
to a newer revision, broadcasting, and the database guards that hold the rules even if the API is bypassed."""

import json
import uuid

import pytest
from sqlalchemy import func, select, text

import db_factories as f
from app.models import AuditEvent, RadioBulletin, RadioBulletinDecision, RadioBulletinRevision, SourceItem, Story
from newsroom_helpers import (  # noqa: F401  (newsroom_client and room are fixtures)
    AIR,
    B,
    N,
    S,
    approved_story,
    live_bulletin,
    make_article,
    make_bulletin,
    make_staff,
    newsroom_client,
    put_items,
    ready_bulletin,
    revision,
    revision_action,
    room,
    states,
    words,
)

pytestmark = pytest.mark.usefixtures("migrated_engine")

CHECK, UNIQUE, FOREIGN_KEY, RESTRICT = "23514", "23505", "23503", "23001"


# ---- mode gating, access and the role matrix -------------------------------------------------------------------


def test_bulletin_routes_do_not_exist_in_road_safety_mode(client):
    assert client.get(B).status_code == 404
    assert client.get(f"{B}/{uuid.uuid4()}").status_code == 404


def test_anonymous_users_are_turned_away(newsroom_client):
    assert newsroom_client.get(B).status_code == 401
    assert newsroom_client.post(B, json={}).status_code in (401, 403)


def test_everyone_signed_in_can_read_but_only_the_executive_producer_can_change(room, session):
    bulletin, _ = ready_bulletin(room, session)
    bid = bulletin["id"]
    for user in (room.reporter, room.analyst):
        room.as_(user)
        assert room.get(B).json()["total"] == 1
        assert room.get(f"{B}/{bid}").status_code == 200
        assert room.post(B, {"name": "x", "scheduled_for": AIR, "target_seconds": 60}).status_code == 403
        assert room.post(f"{B}/{bid}/revisions").status_code == 403
        assert put_items(room, bid, 1, []).status_code == 403
        assert revision_action(room, bid, 1, "submit").status_code == 403
        assert revision_action(room, bid, 1, "approve").status_code == 403
        assert revision_action(room, bid, 1, "reject", {"comment": "no"}).status_code == 403
        assert room.post(f"{B}/{bid}/broadcast").status_code == 403
    assert states(room.as_(room.ep).get(f"{B}/{bid}").json()) == {1: "pending_approval"}


def test_a_reporter_can_never_approve_a_bulletin(room, session):
    bulletin, _ = ready_bulletin(room, session)
    room.as_(room.reporter)
    assert revision_action(room, bulletin["id"], 1, "approve").status_code == 403
    assert states(room.get(f"{B}/{bulletin['id']}").json()) == {1: "pending_approval"}


def test_a_missing_bulletin_or_revision_is_a_404(room, session):
    bulletin = make_bulletin(room)
    assert room.get(f"{B}/{uuid.uuid4()}").json()["error"]["code"] == "BULLETIN_NOT_FOUND"
    assert revision_action(room, bulletin["id"], 9, "submit").json()["error"]["code"] == "REVISION_NOT_FOUND"
    assert put_items(room, bulletin["id"], 9, []).status_code == 404


# ---- creating --------------------------------------------------------------------------------------------------


def test_a_bulletin_starts_with_an_empty_draft_revision(room):
    bulletin = make_bulletin(room, name="  Breakfast bulletin ", target_seconds=300)
    assert bulletin["name"] == "Breakfast bulletin" and bulletin["target_seconds"] == 300
    assert bulletin["created_by"]["id"] == str(room.ep.id)
    assert bulletin["approved_revision_number"] is None and bulletin["approved_at"] is None
    assert bulletin["latest_revision_number"] == 1 and bulletin["latest_revision_state"] == "draft"
    (first,) = bulletin["revisions"]
    assert first["revision_number"] == 1 and first["state"] == "draft" and first["items"] == [] and first["total_seconds"] == 0


@pytest.mark.parametrize(
    "overrides",
    [{"name": "   "}, {"name": ""}, {"target_seconds": 5}, {"target_seconds": 99999}, {"scheduled_for": "2099-01-01T16:00:00"},
     {"scheduled_for": "not a date"}],
)
def test_bad_bulletins_are_refused(room, overrides):
    room.as_(room.ep)
    body = {"name": "News", "scheduled_for": AIR, "target_seconds": 300, **overrides}
    assert room.post(B, body).status_code == 422


# ---- building the running order ---------------------------------------------------------------------------------


def test_stories_are_pinned_to_their_approved_script_in_the_order_given(room, session):
    bulletin = make_bulletin(room, target_seconds=120)
    (s1, sc1), (s2, sc2), (s3, sc3) = (approved_story(room, session) for _ in range(3))
    room.as_(room.ep)
    saved = put_items(room, bulletin["id"], 1, [{"story_id": s3}, {"story_id": s1}, {"story_id": s2}]).json()
    items = revision(saved, 1)["items"]
    assert [i["story"]["id"] for i in items] == [s3, s1, s2]
    assert [i["position"] for i in items] == [1, 2, 3]
    assert [i["script"]["id"] for i in items] == [sc3, sc1, sc2]
    assert all(i["script_approved"] and i["script"]["version_number"] == 1 for i in items)
    assert all(i["duration_seconds"] == 30 and not i["duration_overridden"] for i in items)
    assert revision(saved, 1)["total_seconds"] == 90 and saved["target_seconds"] == 120


def test_a_clip_can_override_the_duration_and_carry_a_note(room, session):
    bulletin = make_bulletin(room)
    story_id, _ = approved_story(room, session)
    other_id, _ = approved_story(room, session)
    room.as_(room.ep)
    saved = put_items(room, bulletin["id"], 1, [
        {"story_id": story_id, "duration_override_seconds": 45, "note": "  Play clip 3 after the intro "},
        {"story_id": other_id},
    ]).json()
    first, second = revision(saved, 1)["items"]
    assert first["duration_seconds"] == 45 and first["duration_overridden"] is True
    assert first["note"] == "Play clip 3 after the intro" and second["note"] is None
    assert revision(saved, 1)["total_seconds"] == 75  # 45 for the clip + 30 estimated
    assert put_items(room, bulletin["id"], 1, [{"story_id": story_id, "duration_override_seconds": 0}]).status_code == 422


def test_saving_replaces_the_whole_running_order(room, session):
    bulletin = make_bulletin(room)
    a, _ = approved_story(room, session)
    b, _ = approved_story(room, session)
    room.as_(room.ep)
    put_items(room, bulletin["id"], 1, [{"story_id": a}, {"story_id": b}])
    reordered = put_items(room, bulletin["id"], 1, [{"story_id": b}, {"story_id": a}]).json()
    assert [i["story"]["id"] for i in revision(reordered, 1)["items"]] == [b, a]
    only_b = put_items(room, bulletin["id"], 1, [{"story_id": b}]).json()
    assert [i["story"]["id"] for i in revision(only_b, 1)["items"]] == [b]
    assert revision(put_items(room, bulletin["id"], 1, []).json(), 1)["items"] == []


def test_the_running_order_rejects_bad_entries(room, session):
    bulletin = make_bulletin(room)
    story_id, script_id = approved_story(room, session)
    other_id, other_script = approved_story(room, session)
    dropped_id, _ = approved_story(room, session)
    room.as_(room.reporter)
    assert room.post(f"{S}/{dropped_id}/drop").status_code == 200
    unscripted = room.take(room.reporter, title="No script yet")
    room.as_(room.ep)
    bid = bulletin["id"]
    assert put_items(room, bid, 1, [{"story_id": story_id}, {"story_id": story_id}]).json()["error"]["code"] == "DUPLICATE_STORY"
    assert put_items(room, bid, 1, [{"story_id": str(uuid.uuid4())}]).json()["error"]["code"] == "STORY_NOT_FOUND"
    assert put_items(room, bid, 1, [{"story_id": dropped_id}]).json()["error"]["code"] == "STORY_DROPPED"
    assert put_items(room, bid, 1, [{"story_id": unscripted}]).json()["error"]["code"] == "STORY_HAS_NO_SCRIPT"
    wrong = put_items(room, bid, 1, [{"story_id": story_id, "script_id": other_script}])
    assert wrong.status_code == 422 and wrong.json()["error"]["code"] == "SCRIPT_NOT_FOUND"  # another story's script
    assert put_items(room, bid, 1, [{"story_id": story_id, "script_id": script_id}]).status_code == 200
    # nothing half-saved by the refused attempts
    assert [i["story"]["id"] for i in revision(room.get(f"{B}/{bid}").json(), 1)["items"]] == [story_id]


def test_a_story_still_awaiting_approval_can_be_lined_up_but_not_submitted(room, session):
    bulletin = make_bulletin(room)
    waiting = room.take(room.reporter, make_article(session))
    room.verify(waiting)
    room.script(waiting)
    room.submit(waiting)
    ready, _ = approved_story(room, session)
    room.as_(room.ep)
    saved = put_items(room, bulletin["id"], 1, [{"story_id": ready}, {"story_id": waiting}]).json()
    unapproved = revision(saved, 1)["items"][1]
    assert unapproved["script"]["version_number"] == 1 and unapproved["script_approved"] is False  # pinned to the newest
    refused = revision_action(room, bulletin["id"], 1, "submit")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "SCRIPT_NOT_APPROVED"
    assert refused.json()["error"]["details"][0]["field"] == "items.2"  # names the position
    assert "has not been approved" in refused.json()["error"]["details"][0]["message"]
    assert states(room.get(f"{B}/{bulletin['id']}").json()) == {1: "draft"}
    # once the Executive Producer approves that script, the same pin can be submitted
    assert room.review(waiting, 1).status_code == 200
    assert revision_action(room, bulletin["id"], 1, "submit").status_code == 200


# ---- submitting ------------------------------------------------------------------------------------------------


def test_an_empty_bulletin_cannot_be_submitted(room):
    bulletin = make_bulletin(room)
    refused = revision_action(room, bulletin["id"], 1, "submit")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "EMPTY_BULLETIN"


def test_a_rewritten_story_is_flagged_but_the_approved_version_is_still_what_is_read(room, session):
    bulletin, ids = ready_bulletin(room, session, stories=1)
    room.as_(room.reporter)
    room.script(ids[0], body=words(10), base=1)  # a reporter rewrites the approved story: version 2, a draft
    room.as_(room.ep)
    item = revision(room.get(f"{B}/{bulletin['id']}").json(), 1)["items"][0]
    assert item["script"]["version_number"] == 1 and item["script_approved"] is True
    assert item["newer_script_version"] == 2  # the builder flags it
    # a flag, not a block: the approved version 1 is still exactly what was approved and what will be read
    assert revision_action(room, bulletin["id"], 1, "approve").status_code == 200
    assert revision(room.get(f"{B}/{bulletin['id']}").json(), 1)["items"][0]["script"]["version_number"] == 1


def test_a_pinned_script_that_was_never_approved_blocks_submission_even_after_a_rewrite(room, session):
    bulletin = make_bulletin(room)
    story_id = room.take(room.reporter, make_article(session))
    room.verify(story_id)
    room.script(story_id)  # version 1, never submitted
    room.as_(room.ep)
    put_items(room, bulletin["id"], 1, [{"story_id": story_id}])
    room.as_(room.reporter)
    room.script(story_id, body=words(20), base=1)  # version 2 now exists; the pin is still version 1
    room.as_(room.ep)
    item = revision(room.get(f"{B}/{bulletin['id']}").json(), 1)["items"][0]
    assert item["script"]["version_number"] == 1 and item["newer_script_version"] == 2 and item["script_approved"] is False
    assert revision_action(room, bulletin["id"], 1, "submit").json()["error"]["code"] == "SCRIPT_NOT_APPROVED"


def test_a_story_dropped_after_it_was_lined_up_blocks_submission(room, session):
    bulletin = make_bulletin(room)
    story_id, _ = approved_story(room, session)
    room.as_(room.ep)
    put_items(room, bulletin["id"], 1, [{"story_id": story_id}])
    room.as_(room.reporter)
    room.post(f"{S}/{story_id}/drop")
    room.as_(room.ep)
    refused = revision_action(room, bulletin["id"], 1, "submit")
    assert refused.status_code == 409 and "dropped" in refused.json()["error"]["details"][0]["message"]


def test_a_submitted_revision_is_locked(room, session):
    bulletin, ids = ready_bulletin(room, session, stories=1)
    detail = room.get(f"{B}/{bulletin['id']}").json()
    pending = revision(detail, 1)
    assert pending["state"] == "pending_approval" and pending["submitted_by"]["id"] == str(room.ep.id) and pending["submitted_at"]
    locked = put_items(room, bulletin["id"], 1, [])
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "REVISION_LOCKED"
    assert revision_action(room, bulletin["id"], 1, "submit").status_code == 409  # not a draft any more


# ---- approval and the atomic swap -------------------------------------------------------------------------------


def test_approving_makes_the_revision_the_live_one(room, session):
    bulletin, _ = ready_bulletin(room, session, target_seconds=120)
    approved = revision_action(room, bulletin["id"], 1, "approve", {"comment": "Good"}).json()
    assert approved["approved_revision_number"] == 1 and approved["approved_at"] and approved["approved_total_seconds"] == 60
    first = revision(approved, 1)
    assert first["state"] == "approved" and first["approved_by"]["id"] == str(room.ep.id) and first["approved_at"]
    (decision,) = first["decisions"]
    assert decision["decision"] == "approved" and decision["comment"] == "Good" and decision["reviewer"]["id"] == str(room.ep.id)
    assert approved["latest_revision_state"] == "approved" and approved["aired_at"] is None


def test_approving_what_you_submitted_is_allowed_but_flagged_and_a_second_approver_is_not_self_approval(room, session):
    other_ep = make_staff(session, "editor")
    first, _ = ready_bulletin(room, session, stories=1)
    assert revision(revision_action(room, first["id"], 1, "approve").json(), 1)["decisions"][0]["self_approved"] is True
    second, _ = ready_bulletin(room, session, stories=1, name="Noon")
    room.as_(other_ep)
    assert revision(revision_action(room, second["id"], 1, "approve").json(), 1)["decisions"][0]["self_approved"] is False
    row = session.scalar(select(RadioBulletinDecision).where(RadioBulletinDecision.reviewer_id == other_ep.id))
    assert row.self_approved is False


def test_only_a_submitted_revision_can_be_approved_or_rejected(room, session):
    bulletin = make_bulletin(room)
    assert revision_action(room, bulletin["id"], 1, "approve").json()["error"]["code"] == "INVALID_STATE"  # a draft
    assert revision_action(room, bulletin["id"], 1, "reject", {"comment": "no"}).json()["error"]["code"] == "INVALID_STATE"
    live, _ = live_bulletin(room, session, stories=1)
    assert revision_action(room, live["id"], 1, "approve").status_code == 409  # already approved


def test_rejecting_needs_a_comment_and_a_rejected_revision_can_be_replaced(room, session):
    bulletin, ids = ready_bulletin(room, session, stories=1)
    assert revision_action(room, bulletin["id"], 1, "reject", {"comment": "   "}).status_code == 422
    assert revision_action(room, bulletin["id"], 1, "reject", {}).status_code == 422
    rejected = revision_action(room, bulletin["id"], 1, "reject", {"comment": "Too long for the slot"}).json()
    assert states(rejected) == {1: "rejected"} and rejected["approved_revision_number"] is None
    decision = revision(rejected, 1)["decisions"][0]
    assert decision["decision"] == "rejected" and decision["comment"] == "Too long for the slot" and decision["self_approved"] is False
    # no approved revision, so the next one starts from the newest (the rejected) one
    again = room.post(f"{B}/{bulletin['id']}/revisions")
    assert again.status_code == 201
    assert states(again.json()) == {1: "rejected", 2: "draft"}
    assert [i["story"]["id"] for i in revision(again.json(), 2)["items"]] == ids


def test_a_new_revision_copies_the_approved_one_and_the_approved_one_stays_live(room, session):
    bulletin, ids = live_bulletin(room, session)
    created = room.post(f"{B}/{bulletin['id']}/revisions")
    assert created.status_code == 201
    detail = created.json()
    assert states(detail) == {1: "approved", 2: "draft"}
    assert detail["approved_revision_number"] == 1 and detail["latest_revision_number"] == 2
    assert [i["story"]["id"] for i in revision(detail, 2)["items"]] == ids  # copied
    assert [i["script"]["id"] for i in revision(detail, 2)["items"]] == [i["script"]["id"] for i in revision(detail, 1)["items"]]
    # editing the new draft never touches the approved revision
    put_items(room, bulletin["id"], 2, [{"story_id": ids[1]}])
    after = room.get(f"{B}/{bulletin['id']}").json()
    assert len(revision(after, 1)["items"]) == 2 and len(revision(after, 2)["items"]) == 1
    assert after["approved_revision_number"] == 1 and revision(after, 1)["state"] == "approved"
    # the approved revision itself can never be edited in place
    assert put_items(room, bulletin["id"], 1, []).json()["error"]["code"] == "REVISION_LOCKED"


def test_only_one_revision_can_be_open_at_a_time(room, session):
    bulletin, _ = live_bulletin(room, session, stories=1)
    assert room.post(f"{B}/{bulletin['id']}/revisions").status_code == 201
    second = room.post(f"{B}/{bulletin['id']}/revisions")
    assert second.status_code == 409 and second.json()["error"]["code"] == "REVISION_ALREADY_OPEN"
    assert revision_action(room, bulletin["id"], 2, "submit").status_code == 200
    third = room.post(f"{B}/{bulletin['id']}/revisions")  # still open while it waits for approval
    assert third.status_code == 409 and third.json()["error"]["code"] == "REVISION_ALREADY_OPEN"


def test_approving_revision_two_atomically_supersedes_revision_one(room, session):
    bulletin, ids = live_bulletin(room, session)
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[0]}])
    revision_action(room, bid, 2, "submit")
    # while revision 2 waits, revision 1 is still the approved, live one
    waiting = room.get(f"{B}/{bid}").json()
    assert states(waiting) == {1: "approved", 2: "pending_approval"} and waiting["approved_revision_number"] == 1

    swapped = revision_action(room, bid, 2, "approve").json()
    assert states(swapped) == {1: "superseded", 2: "approved"}
    assert swapped["approved_revision_number"] == 2 and swapped["approved_total_seconds"] == 30
    bulletin_row = session.get(RadioBulletin, uuid.UUID(bid), populate_existing=True)
    two = session.scalar(select(RadioBulletinRevision).where(RadioBulletinRevision.bulletin_id == bulletin_row.id, RadioBulletinRevision.revision_number == 2))
    assert bulletin_row.approved_revision_id == two.id
    approved_now = session.scalar(select(func.count()).select_from(RadioBulletinRevision).where(
        RadioBulletinRevision.bulletin_id == bulletin_row.id, RadioBulletinRevision.state == "approved"))
    assert approved_now == 1  # exactly one approved revision, never two and never none
    superseded = next(e for e in session.scalars(select(AuditEvent).where(AuditEvent.action == "newsroom.bulletin_approved")) if e.details["revision"] == 2)
    assert superseded.details["superseded_revision"] == 1


def test_a_rejected_second_revision_leaves_the_first_one_live(room, session):
    bulletin, ids = live_bulletin(room, session)
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[0]}])
    revision_action(room, bid, 2, "submit")
    rejected = revision_action(room, bid, 2, "reject", {"comment": "Keep both stories"}).json()
    assert states(rejected) == {1: "approved", 2: "rejected"} and rejected["approved_revision_number"] == 1
    # a rejected revision is closed, so a new one can be started from the approved one
    assert room.post(f"{B}/{bid}/revisions").status_code == 201


# ---- broadcast -------------------------------------------------------------------------------------------------


def test_broadcasting_marks_stories_broadcast_and_their_articles_used(room, session):
    bulletin, ids = live_bulletin(room, session)
    aired = room.post(f"{B}/{bulletin['id']}/broadcast")
    assert aired.status_code == 200
    detail = aired.json()
    assert detail["aired_at"] and revision(detail, 1)["aired_at"] and revision(detail, 1)["aired_by"]["id"] == str(room.ep.id)
    assert revision(detail, 1)["state"] == "approved"  # airing does not change the approval
    for story_id in ids:
        story = session.get(Story, uuid.UUID(story_id), populate_existing=True)
        assert story.stage == "broadcast"
        article = session.get(SourceItem, story.source_item_id, populate_existing=True)
        review = article.source_metadata["newsroom_review"]
        assert review["status"] == "used" and review["by_id"] == str(room.ep.id)
    # the article page reflects it through the existing review flag
    article_id = session.get(Story, uuid.UUID(ids[0])).source_item_id
    assert room.get(f"{N}/articles/{article_id}").json()["review"]["status"] == "used"


def test_a_revision_can_only_be_broadcast_once_and_only_when_approved(room, session):
    unapproved = make_bulletin(room)
    refused = room.post(f"{B}/{unapproved['id']}/broadcast")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NOT_APPROVED"
    bulletin, _ = live_bulletin(room, session, stories=1)
    assert room.post(f"{B}/{bulletin['id']}/broadcast").status_code == 200
    again = room.post(f"{B}/{bulletin['id']}/broadcast")
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_AIRED"


def test_a_story_reopened_with_a_newer_script_is_not_marked_broadcast_by_the_old_one(room, session):
    bulletin, ids = live_bulletin(room, session, stories=2)
    room.as_(room.reporter)
    room.script(ids[0], body=words(12), base=1)  # reopened: back to drafting with an unapproved version 2
    room.as_(room.ep)
    room.post(f"{B}/{bulletin['id']}/broadcast")
    stages = {s: session.get(Story, uuid.UUID(s), populate_existing=True).stage for s in ids}
    assert stages[ids[0]] == "drafting" and stages[ids[1]] == "broadcast"


def test_after_airing_a_change_needs_a_new_revision(room, session):
    bulletin, ids = live_bulletin(room, session, stories=1)
    room.post(f"{B}/{bulletin['id']}/broadcast")
    assert put_items(room, bulletin["id"], 1, []).json()["error"]["code"] == "REVISION_LOCKED"
    created = room.post(f"{B}/{bulletin['id']}/revisions")
    assert created.status_code == 201 and states(created.json()) == {1: "approved", 2: "draft"}


# ---- listing ---------------------------------------------------------------------------------------------------


def test_the_list_filters_and_orders_bulletins(room, session):
    morning = make_bulletin(room, name="Morning news", scheduled_for="2099-03-01T06:00:00Z")
    noon, _ = live_bulletin(room, session, stories=1, name="Noon news", scheduled_for="2099-03-01T12:00:00Z")
    evening, _ = live_bulletin(room, session, stories=1, name="Evening sport", scheduled_for="2099-03-01T18:00:00Z")
    room.post(f"{B}/{evening['id']}/broadcast")
    ids = lambda **p: [b["name"] for b in room.get(B, params=p).json()["items"]]  # noqa: E731
    assert ids() == ["Evening sport", "Noon news", "Morning news"]  # latest air time first
    assert ids(order="asc") == ["Morning news", "Noon news", "Evening sport"]
    assert ids(q="news") == ["Noon news", "Morning news"] and ids(q="100%_") == []
    assert ids(has_approved="true") == ["Evening sport", "Noon news"] and ids(has_approved="false") == ["Morning news"]
    assert ids(aired="true") == ["Evening sport"] and set(ids(aired="false")) == {"Noon news", "Morning news"}
    assert ids(scheduled_from="2099-03-01T10:00:00Z", scheduled_to="2099-03-01T14:00:00Z") == ["Noon news"]
    page = room.get(B, params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1
    summary = next(b for b in room.get(B).json()["items"] if b["name"] == "Noon news")
    assert summary["approved_revision_number"] == 1 and summary["approved_total_seconds"] == 30 and summary["aired_at"] is None
    assert next(b for b in room.get(B).json()["items"] if b["name"] == "Evening sport")["aired_at"]


# ---- audit -----------------------------------------------------------------------------------------------------


def test_every_bulletin_change_is_audited_with_ids_and_state_only(room, session):
    bulletin, ids = live_bulletin(room, session, stories=1, name="Secret bulletin name")
    bid = bulletin["id"]
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": ids[0], "note": "Secret clip note"}])
    revision_action(room, bid, 2, "submit")
    revision_action(room, bid, 2, "reject", {"comment": "Secret comment"})
    room.post(f"{B}/{bid}/broadcast")
    actions = {e.action for e in session.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(bid)))}
    assert actions == {
        "newsroom.bulletin_created", "newsroom.bulletin_items_saved", "newsroom.bulletin_submitted",
        "newsroom.bulletin_approved", "newsroom.bulletin_revision_created", "newsroom.bulletin_rejected",
        "newsroom.bulletin_aired",
    }
    everything = json.dumps([e.details for e in session.scalars(select(AuditEvent))])
    assert not any(secret in everything for secret in ("Secret bulletin name", "Secret clip note", "Secret comment"))
    article_events = list(session.scalars(select(AuditEvent).where(AuditEvent.action == "newsroom.article_reviewed")))
    assert article_events and article_events[0].details["via"] == "broadcast"


def test_refused_requests_write_no_bulletin_audit_events(room, session):
    bulletin = make_bulletin(room)
    count = lambda: session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("newsroom.bulletin%")))  # noqa: E731
    before = count()
    revision_action(room, bulletin["id"], 1, "submit")  # empty
    revision_action(room, bulletin["id"], 1, "approve")  # not submitted
    room.post(f"{B}/{bulletin['id']}/broadcast")  # not approved
    room.as_(room.reporter)
    room.post(f"{B}/{bulletin['id']}/revisions")  # not allowed
    assert count() == before


# ---- database guards (the rules hold even if the application is bypassed) -----------------------------------


def revision_id(session, bulletin, number):
    return session.scalar(select(RadioBulletinRevision.id).where(
        RadioBulletinRevision.bulletin_id == uuid.UUID(bulletin["id"]), RadioBulletinRevision.revision_number == number))


def test_the_items_of_a_revision_that_left_draft_cannot_change(room, session, db_error):
    bulletin, ids = live_bulletin(room, session, stories=1)
    rid = revision_id(session, bulletin, 1)
    other_story = approved_story(room, session)
    with db_error(session, RESTRICT):
        session.execute(text("UPDATE radio_bulletin_items SET note = 'sneaky' WHERE revision_id = :r"), {"r": rid})
    with db_error(session, RESTRICT):
        session.execute(text("DELETE FROM radio_bulletin_items WHERE revision_id = :r"), {"r": rid})
    with db_error(session, RESTRICT):
        session.execute(
            text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id) "
                 "SELECT :r, 9, s.story_id, s.id FROM story_scripts s WHERE s.story_id = :s LIMIT 1"),
            {"r": rid, "s": uuid.UUID(other_story[0])},
        )
    # pending revisions are frozen too, not only approved ones
    pending, _ = ready_bulletin(room, session, stories=1, name="Pending one")
    with db_error(session, RESTRICT):
        session.execute(text("DELETE FROM radio_bulletin_items WHERE revision_id = :r"), {"r": revision_id(session, pending, 1)})
    assert session.scalar(text("SELECT count(*) FROM radio_bulletin_items")) == 2  # one in each bulletin, untouched


def test_a_decision_is_append_only_and_needs_an_active_human_editor(room, session, db_error):
    bulletin, _ = live_bulletin(room, session, stories=1)
    rid = revision_id(session, bulletin, 1)
    with db_error(session, RESTRICT):
        session.execute(text("UPDATE radio_bulletin_decisions SET comment = 'rewritten'"))
    with db_error(session, RESTRICT):
        session.execute(text("DELETE FROM radio_bulletin_decisions"))
    inactive = f.make_user(session, "editor", is_active=False)
    for who in (room.reporter, room.analyst, inactive, f.make_user(session, "service")):
        with db_error(session, CHECK):
            session.add(RadioBulletinDecision(revision_id=rid, reviewer_id=who.id, decision="approved"))


def test_decision_rules_are_checked_by_the_database(room, session, db_error):
    bulletin, _ = live_bulletin(room, session, stories=1)
    rid = revision_id(session, bulletin, 1)
    with db_error(session, CHECK):  # rejecting needs a comment
        session.add(RadioBulletinDecision(revision_id=rid, reviewer_id=room.ep.id, decision="rejected"))
    with db_error(session, CHECK):  # a rejection cannot be flagged as self-approval
        session.add(RadioBulletinDecision(revision_id=rid, reviewer_id=room.ep.id, decision="rejected", comment="no", self_approved=True))
    with db_error(session, CHECK):
        session.add(RadioBulletinDecision(revision_id=rid, reviewer_id=room.ep.id, decision="maybe"))


def test_a_revision_cannot_be_approved_without_a_decision_or_skip_a_state(room, session, db_error):
    bulletin, _ = ready_bulletin(room, session, stories=1)
    rid = revision_id(session, bulletin, 1)
    with db_error(session, CHECK):  # pending -> approved needs an approving decision
        session.execute(text("UPDATE radio_bulletin_revisions SET state = 'approved', approved_by = :u, approved_at = now() WHERE id = :r"),
                        {"r": rid, "u": room.ep.id})
    with db_error(session, CHECK):  # ... and a rejection needs a rejecting one
        session.execute(text("UPDATE radio_bulletin_revisions SET state = 'rejected' WHERE id = :r"), {"r": rid})
    draft = make_bulletin(room, name="A draft")
    with db_error(session, CHECK):  # a draft cannot jump straight to approved
        session.execute(text("UPDATE radio_bulletin_revisions SET state = 'approved' WHERE id = :r"), {"r": revision_id(session, draft, 1)})
    live, _ = live_bulletin(room, session, stories=1, name="Live one")
    with db_error(session, CHECK):  # approved only moves forward, to superseded
        session.execute(text("UPDATE radio_bulletin_revisions SET state = 'draft' WHERE id = :r"), {"r": revision_id(session, live, 1)})
    with db_error(session, CHECK):  # a revision is born a draft
        session.execute(text("INSERT INTO radio_bulletin_revisions (bulletin_id, revision_number, state, created_by) "
                             "VALUES (:b, 7, 'approved', :u)"), {"b": uuid.UUID(draft["id"]), "u": room.ep.id})


def test_two_approved_revisions_are_impossible(room, session, db_error):
    bulletin, ids = live_bulletin(room, session, stories=1)
    bid = uuid.UUID(bulletin["id"])
    room.post(f"{B}/{bulletin['id']}/revisions")
    one, two = revision_id(session, bulletin, 1), revision_id(session, bulletin, 2)
    # a second approved revision cannot be created beside the first, not even with a decision on file
    session.add(RadioBulletinDecision(revision_id=two, reviewer_id=room.ep.id, decision="approved"))
    session.flush()
    session.execute(text("UPDATE radio_bulletin_revisions SET state = 'pending_approval', submitted_by = :u, submitted_at = now() WHERE id = :r"),
                    {"r": two, "u": room.ep.id})
    with db_error(session, UNIQUE):
        session.execute(text("UPDATE radio_bulletin_revisions SET state = 'approved', approved_by = :u, approved_at = now() WHERE id = :r"),
                        {"r": two, "u": room.ep.id})
    assert session.scalar(select(func.count()).select_from(RadioBulletinRevision).where(
        RadioBulletinRevision.bulletin_id == bid, RadioBulletinRevision.state == "approved")) == 1
    assert one != two


def test_only_one_revision_per_bulletin_can_be_open(room, session, db_error):
    bulletin = make_bulletin(room)
    with db_error(session, UNIQUE):
        session.execute(text("INSERT INTO radio_bulletin_revisions (bulletin_id, revision_number, created_by) VALUES (:b, 2, :u)"),
                        {"b": uuid.UUID(bulletin["id"]), "u": room.ep.id})


def test_the_approved_pointer_can_only_name_an_approved_revision_of_the_same_bulletin(room, session, db_error):
    live, _ = live_bulletin(room, session, stories=1, name="One")
    other, _ = live_bulletin(room, session, stories=1, name="Two")
    pending, _ = ready_bulletin(room, session, stories=1, name="Pending")
    draft = make_bulletin(room, name="Draft")
    with db_error(session, CHECK):  # no approving decision for that revision
        session.execute(text("UPDATE radio_bulletins SET approved_revision_id = :r WHERE id = :b"),
                        {"r": revision_id(session, draft, 1), "b": uuid.UUID(draft["id"])})
    with db_error(session, CHECK):  # a pending revision is not an approved one
        session.execute(text("UPDATE radio_bulletins SET approved_revision_id = :r WHERE id = :b"),
                        {"r": revision_id(session, pending, 1), "b": uuid.UUID(pending["id"])})
    with db_error(session, FOREIGN_KEY):  # another bulletin's approved revision
        session.execute(text("UPDATE radio_bulletins SET approved_revision_id = :r WHERE id = :b"),
                        {"r": revision_id(session, other, 1), "b": uuid.UUID(live["id"])})
    current = session.scalar(select(RadioBulletin.approved_revision_id).where(RadioBulletin.id == uuid.UUID(live["id"])))
    assert current == revision_id(session, live, 1)  # untouched by every refused attempt


def test_bulletin_data_rules_are_checked_by_the_database(room, session, db_error):
    make_bulletin(room)
    with db_error(session, CHECK):
        session.execute(text("INSERT INTO radio_bulletins (name, scheduled_for, target_seconds, created_by) VALUES ('  ', now(), 60, :u)"), {"u": room.ep.id})
    with db_error(session, CHECK):
        session.execute(text("INSERT INTO radio_bulletins (name, scheduled_for, target_seconds, created_by) VALUES ('x', now(), 0, :u)"), {"u": room.ep.id})
    bulletin, ids = live_bulletin(room, session, stories=1, name="Items")
    _, other_script = approved_story(room, session)  # another story's script
    draft = make_bulletin(room, name="Draft items")
    did = revision_id(session, draft, 1)
    with db_error(session, FOREIGN_KEY):  # a pinned script must belong to the item's story
        session.execute(text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id) VALUES (:r, 1, :s, :c)"),
                        {"r": did, "s": uuid.UUID(ids[0]), "c": other_script})
    script = session.scalar(text("SELECT id FROM story_scripts WHERE story_id = :s"), {"s": uuid.UUID(ids[0])})
    with db_error(session, CHECK):
        session.execute(text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id) VALUES (:r, 0, :s, :c)"),
                        {"r": did, "s": uuid.UUID(ids[0]), "c": script})
    with db_error(session, CHECK):
        session.execute(text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id, duration_override_seconds) VALUES (:r, 1, :s, :c, 0)"),
                        {"r": did, "s": uuid.UUID(ids[0]), "c": script})
    session.execute(text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id) VALUES (:r, 1, :s, :c)"),
                    {"r": did, "s": uuid.UUID(ids[0]), "c": script})
    with db_error(session, UNIQUE):  # a story once per revision, a position once per revision
        session.execute(text("INSERT INTO radio_bulletin_items (revision_id, position, story_id, script_id) VALUES (:r, 2, :s, :c)"),
                        {"r": did, "s": uuid.UUID(ids[0]), "c": script})
