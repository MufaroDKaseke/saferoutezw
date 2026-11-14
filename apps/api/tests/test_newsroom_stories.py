"""NUST FM story workflow: roles, taking an article, verification, script versions, review, and the
database guards behind them. Everything is synthetic; nothing calls OpenAI."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import func, inspect, select, text

import db_factories as f
from app.models import AuditEvent, Story, StoryReview, StoryScript
from app.services.newsroom_workflow import estimate_seconds
from conftest import alembic_config
from newsroom_helpers import (  # noqa: F401  (newsroom_client and room are fixtures)
    N,
    S,
    login_as,
    make_article,
    make_staff,
    newsroom_client,
    room,
    words,
)

pytestmark = pytest.mark.usefixtures("migrated_engine")

CHECK, UNIQUE, RESTRICT = "23514", "23505", "23001"


# ---- mode gating, access and the role matrix -------------------------------------------------------------------


def test_story_routes_do_not_exist_in_road_safety_mode(client):
    assert client.get(S).status_code == 404
    assert client.get(f"{N}/assignees").status_code == 404


def test_anonymous_users_are_turned_away(newsroom_client):
    assert newsroom_client.get(S).status_code == 401
    assert newsroom_client.post(S, json={"title": "x"}).status_code in (401, 403)


def test_analysts_can_read_every_story_but_change_nothing(room, session):
    story_id = room.take(room.reporter, make_article(session))
    room.as_(room.analyst)
    assert room.get(S).json()["total"] == 1
    assert room.get(f"{S}/{story_id}").status_code == 200
    assert room.post(S, {"title": "Analyst story"}).status_code == 403
    for action, body in (("verify", {"note": "note"}), ("scripts", {"headline": "h", "body": "b"}),
                         ("submit", None), ("drop", None)):
        assert room.post(f"{S}/{story_id}/{action}", body).status_code == 403, action
    assert room.review(story_id, 1).status_code == 403
    assert room.patch(f"{S}/{story_id}", {"title": "Renamed"}).status_code == 403


def test_a_reporter_cannot_approve_even_their_own_story(room):
    story_id = room.ready_for_review()
    room.as_(room.reporter)
    assert room.review(story_id, 1).status_code == 403
    assert room.review(story_id, 1, "changes_requested", "no").status_code == 403
    assert room.get(f"{S}/{story_id}").json()["stage"] == "in_review"


def test_a_reporter_cannot_touch_another_reporters_story(room, session):
    story_id = room.take(room.reporter, make_article(session))
    room.verify(story_id)
    room.as_(room.other)
    assert room.get(f"{S}/{story_id}").status_code == 403
    assert room.get(S).json()["total"] == 0  # not even listed
    assert room.patch(f"{S}/{story_id}", {"title": "Mine now"}).status_code == 403
    for action, body in (("verify", {"note": "note"}), ("scripts", {"headline": "h", "body": "b"}),
                         ("submit", None), ("drop", None)):
        assert room.post(f"{S}/{story_id}/{action}", body).status_code == 403, action
    assert session.scalar(select(Story.stage).where(Story.id == uuid.UUID(story_id))) == "assigned"


def test_the_executive_producer_sees_and_edits_every_story(room, session):
    story_id = room.take(room.reporter, make_article(session))
    room.take(room.other, make_article(session))
    room.as_(room.ep)
    assert room.get(S).json()["total"] == 2
    assert room.get(f"{S}/{story_id}").status_code == 200
    saved = room.script(story_id, headline="EP wrote this")
    assert saved["scripts"][0]["created_by"]["id"] == str(room.ep.id)


def test_reporters_only_list_their_own_stories(room, session):
    mine = room.take(room.reporter, make_article(session))
    room.take(room.other, make_article(session))
    room.as_(room.reporter)
    body = room.get(S).json()
    assert [s["id"] for s in body["items"]] == [mine]
    # asking for someone else's stories does not widen the view
    assert room.get(S, params={"assignee_id": str(room.other.id)}).json()["total"] == 0


def test_reporters_can_read_articles_but_not_triage_them(room, session):
    article = make_article(session)
    room.as_(room.reporter)
    assert room.get(f"{N}/articles").status_code == 200
    assert room.get(f"{N}/articles/{article.id}").status_code == 200
    assert room.patch(f"{N}/articles/{article.id}/review", {"status": "used"}).status_code == 403


def test_admins_can_create_reporter_accounts(room):
    admin = make_staff(room.session, "admin")
    room.as_(admin)
    created = room.post("/api/v1/admin/users", {
        "email": "reporter.new@example.test", "display_name": "New Reporter", "role": "reporter",
        "password": "correct horse battery staple 1",
    })
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "reporter"


# ---- taking an article ------------------------------------------------------------------------------------------


def test_a_reporter_takes_an_article_for_themselves(room, session):
    article = make_article(session, title_redacted="Water shedding extended")
    room.as_(room.reporter)
    response = room.post(S, {"source_item_id": str(article.id)})
    assert response.status_code == 201
    story = response.json()
    assert story["title"] == "Water shedding extended" and story["stage"] == "assigned"
    assert story["assignee"]["id"] == str(room.reporter.id)
    assert story["source_item_id"] == str(article.id) and story["article"]["headline"] == "Water shedding extended"
    assert story["scripts"] == [] and story["reviews"] == [] and story["verification"] is None
    assert story["reading_wpm"] == 150


def test_an_article_can_only_be_taken_once_until_the_story_is_dropped(room, session):
    article = make_article(session)
    first = room.take(room.reporter, article)
    room.as_(room.other)
    clash = room.post(S, {"source_item_id": str(article.id)})
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "ARTICLE_ALREADY_HAS_STORY"
    room.as_(room.reporter)
    assert room.post(f"{S}/{first}/drop").json()["stage"] == "dropped"
    room.as_(room.other)
    assert room.post(S, {"source_item_id": str(article.id)}).status_code == 201


def test_only_the_executive_producer_assigns_stories_to_other_people(room, session):
    article = make_article(session)
    room.as_(room.reporter)
    refused = room.post(S, {"source_item_id": str(article.id), "assignee_id": str(room.other.id)})
    assert refused.status_code == 403
    room.as_(room.ep)
    assigned = room.post(S, {"source_item_id": str(article.id), "assignee_id": str(room.other.id)})
    assert assigned.status_code == 201 and assigned.json()["assignee"]["id"] == str(room.other.id)
    story_id = assigned.json()["id"]
    assert room.patch(f"{S}/{story_id}", {"assignee_id": str(room.reporter.id)}).json()["assignee"]["id"] == str(room.reporter.id)
    room.as_(room.reporter)
    assert room.patch(f"{S}/{story_id}", {"assignee_id": str(room.other.id)}).status_code == 403


def test_a_story_cannot_be_assigned_to_an_analyst_or_an_inactive_user(room, session):
    inactive = f.make_user(session, "reporter", is_active=False)
    session.commit()
    room.as_(room.ep)
    for person in (room.analyst, inactive):
        response = room.post(S, {"title": "Orphan", "assignee_id": str(person.id)})
        assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_ASSIGNEE"


def test_original_stories_need_a_title_and_unknown_articles_are_refused(room):
    room.as_(room.reporter)
    assert room.post(S, {}).json()["error"]["code"] == "TITLE_REQUIRED"
    missing = room.post(S, {"source_item_id": "00000000-0000-0000-0000-000000000000"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "ARTICLE_NOT_FOUND"
    original = room.post(S, {"title": "  Campus open day  "})
    assert original.status_code == 201 and original.json()["title"] == "Campus open day"
    assert original.json()["source_item_id"] is None and original.json()["article"] is None


def test_the_article_page_shows_its_story_and_stage(room, session):
    article = make_article(session)
    room.as_(room.reporter)
    assert room.get(f"{N}/articles/{article.id}").json()["story"] is None
    story_id = room.take(room.reporter, article)
    linked = room.get(f"{N}/articles/{article.id}").json()["story"]
    assert linked["id"] == story_id and linked["stage"] == "assigned"
    assert linked["assignee"]["display_name"] == room.reporter.display_name
    # a reporter who did not take it still sees who did
    room.as_(room.other)
    assert room.get(f"{N}/articles/{article.id}").json()["story"]["id"] == story_id


def test_the_story_list_filters_by_stage_title_and_article(room, session):
    one = room.take(room.reporter, make_article(session, title_redacted="Zebra crossing opens"))
    two = room.take(room.reporter, make_article(session, title_redacted="Dam levels fall"))
    room.verify(two)
    room.script(two)
    room.submit(two)
    room.as_(room.ep)
    ids = lambda **p: {s["id"] for s in room.get(S, params=p).json()["items"]}  # noqa: E731
    assert ids() == {one, two}
    assert ids(stage="in_review") == {two}
    assert ids(stage=["assigned", "in_review"]) == {one, two}
    assert ids(q="zebra") == {one}
    assert ids(q="100%_") == set()
    assert ids(assignee_id=str(room.other.id)) == set()
    assert room.get(S, params={"stage": "nonsense"}).status_code == 422


def test_the_executive_producer_gets_a_picker_of_assignable_people(room):
    room.as_(room.ep)
    people = room.get(f"{N}/assignees").json()
    roles = {p["id"]: p["role"] for p in people}
    assert roles[str(room.reporter.id)] == "reporter" and roles[str(room.ep.id)] == "editor"
    assert str(room.analyst.id) not in roles
    room.as_(room.reporter)
    assert room.get(f"{N}/assignees").status_code == 403


# ---- verification, scripts and submission ---------------------------------------------------------------------------


def test_submitting_needs_a_recorded_verification_and_a_script(room, session):
    story_id = room.take(room.reporter, make_article(session))
    refused = room.post(f"{S}/{story_id}/submit")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NOT_VERIFIED"
    room.verify(story_id)
    refused = room.post(f"{S}/{story_id}/submit")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NO_SCRIPT"
    room.script(story_id)
    submitted = room.submit(story_id)
    assert submitted["stage"] == "in_review"


def test_verification_is_recorded_with_who_and_when(room, session):
    story_id = room.take(room.reporter, make_article(session))
    assert room.post(f"{S}/{story_id}/verify", {"note": "   "}).status_code == 422
    room.verify(story_id, "Confirmed with the town clerk by phone.")
    story = room.get(f"{S}/{story_id}").json()
    assert story["verified"] is True
    assert story["verification"]["note"] == "Confirmed with the town clerk by phone."
    assert story["verification"]["by"]["id"] == str(room.reporter.id) and story["verification"]["at"]


def test_the_first_script_starts_drafting_and_estimates_reading_time(room, session):
    story_id = room.take(room.reporter, make_article(session))
    story = room.script(story_id, body=words(75))
    assert story["stage"] == "drafting"
    script = story["scripts"][0]
    assert script["version_number"] == 1 and script["origin"] == "human" and script["estimated_seconds"] == 30
    assert story["latest_script_version"] == 1 and story["latest_script_seconds"] == 30
    assert story["approved_script_version"] is None


def test_every_save_is_a_new_version_and_stale_editors_are_refused(room, session):
    story_id = room.take(room.reporter, make_article(session))
    room.script(story_id, headline="First")
    stale_first = room.post(f"{S}/{story_id}/scripts", {"headline": "x", "body": "y", "base_version": None})
    assert stale_first.status_code == 409 and stale_first.json()["error"]["code"] == "SCRIPT_VERSION_CONFLICT"
    second = room.script(story_id, headline="Second", base=1)
    assert [s["version_number"] for s in second["scripts"]] == [1, 2]
    assert [s["headline"] for s in second["scripts"]] == ["First", "Second"]  # version 1 is untouched
    stale = room.post(f"{S}/{story_id}/scripts", {"headline": "x", "body": "y", "base_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "SCRIPT_VERSION_CONFLICT"
    assert room.post(f"{S}/{story_id}/scripts", {"headline": " ", "body": "y"}).status_code == 422


def test_a_story_in_review_cannot_be_edited_or_resubmitted(room):
    story_id = room.ready_for_review()
    room.as_(room.reporter)
    edit = room.post(f"{S}/{story_id}/scripts", {"headline": "h", "body": "b", "base_version": 1})
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "INVALID_STAGE"
    assert room.post(f"{S}/{story_id}/submit").status_code == 409
    assert room.post(f"{S}/{story_id}/verify", {"note": "again"}).status_code == 409


def test_reading_time_maths():
    assert estimate_seconds("", 150) == 0 and estimate_seconds("   \n ", 150) == 0
    assert estimate_seconds(words(75), 150) == 30  # 2.5 words a second
    assert estimate_seconds(words(1), 150) == 1  # always rounded up, never 0 for a real script
    assert estimate_seconds(words(151), 150) == 61
    assert estimate_seconds(words(75), 120) == 38
    assert estimate_seconds("two\twords\nacross  lines", 60) == 4  # any whitespace separates words


# ---- review ----------------------------------------------------------------------------------------------------------


def test_the_executive_producer_approves_a_submitted_story(room):
    story_id = room.ready_for_review()
    room.as_(room.ep)
    approved = room.review(story_id, 1, comment="Good to go")
    assert approved.status_code == 200
    story = approved.json()
    assert story["stage"] == "approved" and story["approved_script_version"] == 1
    review = story["reviews"][0]
    assert review["decision"] == "approved" and review["script_version"] == 1
    assert review["reviewer"]["id"] == str(room.ep.id) and review["self_approved"] is False
    assert review["comment"] == "Good to go"


def test_sending_a_story_back_needs_a_comment_and_returns_it_to_the_reporter(room):
    story_id = room.ready_for_review()
    room.as_(room.ep)
    no_comment = room.review(story_id, 1, "changes_requested", "  ")
    assert no_comment.status_code == 422 and no_comment.json()["error"]["code"] == "COMMENT_REQUIRED"
    back = room.review(story_id, 1, "changes_requested", "Attribute the figures to the council.")
    assert back.status_code == 200 and back.json()["stage"] == "changes_requested"
    assert back.json()["approved_script_version"] is None
    # the reporter fixes it and resubmits
    room.as_(room.reporter)
    edited = room.script(story_id, headline="Council approves budget", base=1)
    assert edited["stage"] == "changes_requested"  # stays visible as sent back until it is resubmitted
    assert room.submit(story_id)["stage"] == "in_review"
    room.as_(room.ep)
    assert room.review(story_id, 2).json()["approved_script_version"] == 2


def test_review_refuses_a_script_that_changed_or_a_story_not_in_review(room, session):
    story_id = room.ready_for_review()
    room.as_(room.ep)
    stale = room.review(story_id, 7)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "STALE_SCRIPT"
    early = room.take(room.reporter, make_article(session))
    room.as_(room.ep)
    not_submitted = room.review(early, 1)
    assert not_submitted.status_code == 409 and not_submitted.json()["error"]["code"] == "INVALID_STAGE"
    assert room.review(story_id, 1).status_code == 200
    assert room.review(story_id, 1).status_code == 409  # already decided


def test_the_executive_producer_may_approve_their_own_work_but_it_is_flagged(room, session):
    own = room.take(room.ep, make_article(session))
    room.verify(own)
    room.script(own)
    room.submit(own)
    approved = room.review(own, 1).json()
    assert approved["stage"] == "approved" and approved["reviews"][0]["self_approved"] is True
    row = session.scalar(select(StoryReview).where(StoryReview.story_id == uuid.UUID(own)))
    assert row.self_approved is True


def test_approving_a_script_the_producer_wrote_on_a_reporters_story_is_also_flagged(room):
    story_id = room.take(room.reporter)
    room.verify(story_id)
    room.as_(room.ep)
    room.script(story_id)  # the EP rewrote the script
    room.as_(room.reporter)
    room.submit(story_id)
    room.as_(room.ep)
    assert room.review(story_id, 1).json()["reviews"][0]["self_approved"] is True


def test_editing_an_approved_story_makes_a_new_version_and_returns_it_to_drafting(room):
    story_id = room.ready_for_review()
    room.as_(room.ep)
    room.review(story_id, 1)
    room.as_(room.reporter)
    edited = room.script(story_id, body=words(30), base=1)
    assert edited["stage"] == "drafting"
    assert edited["latest_script_version"] == 2 and edited["scripts"][1]["estimated_seconds"] == 12
    # the approved version stays the approved one until the new version is approved
    assert edited["approved_script_version"] == 1
    room.submit(story_id)
    room.as_(room.ep)
    assert room.review(story_id, 1).status_code == 409  # approving v1 again is stale
    final = room.review(story_id, 2).json()
    assert final["stage"] == "approved" and final["approved_script_version"] == 2
    assert [r["script_version"] for r in final["reviews"]] == [1, 2]


def test_dropping_a_story(room):
    story_id = room.ready_for_review()
    room.as_(room.reporter)
    dropped = room.post(f"{S}/{story_id}/drop")
    assert dropped.status_code == 200 and dropped.json()["stage"] == "dropped"
    assert room.post(f"{S}/{story_id}/drop").status_code == 409
    assert room.post(f"{S}/{story_id}/scripts", {"headline": "h", "body": "b", "base_version": 1}).status_code == 409
    assert room.patch(f"{S}/{story_id}", {"title": "Renamed"}).status_code == 409


def test_title_and_deadline_can_be_changed_and_the_deadline_cleared(room, session):
    story_id = room.take(room.reporter, make_article(session), deadline_at="2026-12-01T09:00:00Z")
    shown = datetime.fromisoformat(room.get(f"{S}/{story_id}").json()["deadline_at"])
    assert shown == datetime(2026, 12, 1, 9, 0, tzinfo=UTC)  # the same instant, whatever offset it is printed in
    changed = room.patch(f"{S}/{story_id}", {"title": "New working title", "deadline_at": None}).json()
    assert changed["title"] == "New working title" and changed["deadline_at"] is None
    untouched = room.patch(f"{S}/{story_id}", {}).json()
    assert untouched["title"] == "New working title"


def test_a_follow_up_points_at_an_earlier_story(room):
    first = room.take(room.reporter, title="Water crisis")
    follow = room.take(room.reporter, title="Water crisis: council responds", follows_story_id=first)
    assert room.get(f"{S}/{follow}").json()["follows_story_id"] == first
    missing = room.post(S, {"title": "x", "follows_story_id": "00000000-0000-0000-0000-000000000000"})
    assert missing.status_code == 404


# ---- audit ----------------------------------------------------------------------------------------------------------


def test_every_change_is_audited_with_ids_and_state_only(room, session):
    story_id = room.ready_for_review()
    room.as_(room.ep)
    room.review(story_id, 1)
    room.as_(room.reporter)
    room.script(story_id, headline="Secret headline text", body="Secret body text " + words(10), base=1)
    room.post(f"{S}/{story_id}/drop")
    actions = [
        e.action for e in session.scalars(select(AuditEvent).where(AuditEvent.entity_id == uuid.UUID(story_id)).order_by(AuditEvent.created_at, AuditEvent.id))
    ]
    assert sorted(set(actions)) == sorted({
        "newsroom.story_created", "newsroom.story_verified", "newsroom.script_saved", "newsroom.story_submitted",
        "newsroom.story_approved", "newsroom.story_dropped",
    })
    assert actions.count("newsroom.script_saved") == 2
    everything = json.dumps([e.details for e in session.scalars(select(AuditEvent))])
    assert "Secret" not in everything and "Called the council" not in everything  # no text, no notes
    approval = session.scalar(select(AuditEvent).where(AuditEvent.action == "newsroom.story_approved"))
    assert approval.actor_user_id == room.ep.id and approval.details["self_approved"] is False


def test_refused_requests_write_no_audit_events(room, session):
    story_id = room.take(room.reporter)
    newsroom_events = select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("newsroom.%"))
    before = session.scalar(newsroom_events)  # (sign-ins are audited too, so count only story events)
    room.as_(room.other)
    room.post(f"{S}/{story_id}/drop")
    room.as_(room.reporter)
    room.post(f"{S}/{story_id}/submit")  # not verified
    assert session.scalar(newsroom_events) == before


# ---- database guards (the rules hold even if the application is bypassed) -------------------------------------


@pytest.fixture
def staged(session):
    """A story with a script and a review, straight in the database."""
    reporter = f.make_user(session, "reporter")
    editor = f.make_user(session, "editor")
    story = Story(title="Guarded", assignee_id=reporter.id)
    session.add(story)
    session.flush()
    script = StoryScript(story_id=story.id, version_number=1, headline="h", body="b", estimated_seconds=1, created_by=reporter.id)
    session.add(script)
    session.flush()
    return story, script, reporter, editor


def test_scripts_and_reviews_are_append_only(session, staged, db_error):
    story, script, _, editor = staged
    review = StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id, decision="approved")
    session.add(review)
    session.flush()
    with db_error(session, RESTRICT):
        script.body = "rewritten after approval"
    with db_error(session, RESTRICT):
        session.delete(script)
    with db_error(session, RESTRICT):
        review.comment = "rewritten history"
    with db_error(session, RESTRICT):
        session.delete(review)
    with db_error(session, RESTRICT):
        session.execute(text("UPDATE story_scripts SET headline = 'x'"))
    with db_error(session, RESTRICT):
        session.execute(text("DELETE FROM story_reviews"))


def test_only_an_active_human_editor_can_record_a_decision(session, staged, db_error):
    story, script, reporter, editor = staged
    inactive = f.make_user(session, "editor", is_active=False)
    service = f.make_user(session, "service")
    for who in (reporter, inactive, service, f.make_user(session, "analyst")):
        with db_error(session, CHECK):
            session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=who.id, decision="approved"))
    session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id, decision="approved"))
    session.flush()  # an active editor is accepted


def test_a_review_must_name_a_script_of_the_same_story(session, staged, db_error):
    story, script, _, editor = staged
    other = Story(title="Other", assignee_id=editor.id)
    session.add(other)
    session.flush()
    with db_error(session, "23503"):
        session.add(StoryReview(story_id=other.id, script_id=script.id, reviewer_id=editor.id, decision="approved"))


def test_review_rules_are_checked_by_the_database(session, staged, db_error):
    story, script, _, editor = staged
    with db_error(session, CHECK):  # sending back needs a comment
        session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id, decision="changes_requested"))
    with db_error(session, CHECK):  # a send-back cannot be flagged as self-approval
        session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id,
                                decision="changes_requested", comment="fix", self_approved=True))
    with db_error(session, CHECK):
        session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id, decision="maybe"))


def test_a_story_cannot_become_approved_without_an_approval_of_its_latest_script(session, staged, db_error):
    story, script, reporter, editor = staged
    with db_error(session, CHECK):
        session.execute(text("UPDATE stories SET stage = 'approved' WHERE id = :id"), {"id": story.id})
    with db_error(session, CHECK):
        session.execute(text("UPDATE stories SET stage = 'broadcast' WHERE id = :id"), {"id": story.id})
    with db_error(session, CHECK):
        session.add(Story(title="Born approved", assignee_id=reporter.id, stage="approved"))
    session.add(StoryReview(story_id=story.id, script_id=script.id, reviewer_id=editor.id, decision="approved"))
    session.flush()
    session.execute(text("UPDATE stories SET stage = 'approved' WHERE id = :id"), {"id": story.id})  # now allowed
    # a newer, unreviewed script means the story is no longer approved-by-the-numbers
    session.execute(text("UPDATE stories SET stage = 'drafting' WHERE id = :id"), {"id": story.id})
    session.add(StoryScript(story_id=story.id, version_number=2, headline="h", body="b2", estimated_seconds=1, created_by=reporter.id))
    session.flush()
    with db_error(session, CHECK):
        session.execute(text("UPDATE stories SET stage = 'approved' WHERE id = :id"), {"id": story.id})


def test_one_open_story_per_article_is_enforced_by_the_database(session, db_error):
    reporter = f.make_user(session, "reporter")
    article = make_article(session)
    first = Story(title="One", assignee_id=reporter.id, source_item_id=article.id)
    session.add(first)
    session.flush()
    with db_error(session, UNIQUE):
        session.add(Story(title="Two", assignee_id=reporter.id, source_item_id=article.id))
    first.stage = "dropped"
    session.flush()
    session.add(Story(title="Two", assignee_id=reporter.id, source_item_id=article.id))  # a dropped story frees it
    session.add(Story(title="No article A", assignee_id=reporter.id))
    session.add(Story(title="No article B", assignee_id=reporter.id))  # original stories never collide
    session.flush()


def test_story_data_rules_are_checked_by_the_database(session, db_error):
    reporter = f.make_user(session, "reporter")
    with db_error(session, CHECK):
        session.add(Story(title="  ", assignee_id=reporter.id))
    with db_error(session, CHECK):
        session.add(Story(title="Bad stage", assignee_id=reporter.id, stage="published"))
    with db_error(session, CHECK):  # a note without who/when
        session.add(Story(title="Half verified", assignee_id=reporter.id, verification_note="called them"))
    story = Story(title="Self follow", assignee_id=reporter.id)
    session.add(story)
    session.flush()
    with db_error(session, CHECK):  # a story cannot follow itself
        session.execute(text("UPDATE stories SET follows_story_id = id WHERE id = :id"), {"id": story.id})


def test_script_data_rules_are_checked_by_the_database(session, staged, db_error):
    story, _, reporter, _ = staged
    base = dict(story_id=story.id, headline="h", body="b", estimated_seconds=1, created_by=reporter.id)
    with db_error(session, UNIQUE):
        session.add(StoryScript(version_number=1, **base))
    with db_error(session, CHECK):
        session.add(StoryScript(version_number=0, **base))
    with db_error(session, CHECK):
        session.add(StoryScript(version_number=2, **{**base, "body": "  "}))
    with db_error(session, CHECK):  # AI metadata only belongs on AI drafts
        session.add(StoryScript(version_number=2, model_name="gpt", **base))
    session.add(StoryScript(version_number=2, origin="ai_draft", model_name="gpt", prompt_version="newsroom-script-v1",
                            input_tokens=10, output_tokens=5, **base))
    session.flush()


def test_the_reporter_role_is_widened_in_and_out_by_the_migration(migrated_engine, test_database_url):
    """Downgrading removes the story tables and turns reporters into (access-less) contributors."""
    cfg = alembic_config(test_database_url)
    with migrated_engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
        conn.execute(text("INSERT INTO users (email, display_name, role) VALUES ('rep@example.test', 'Rep', 'reporter')"))
    try:
        command.downgrade(cfg, "d0f2a4c6e8b3")
        with migrated_engine.connect() as conn:
            assert conn.execute(text("SELECT role FROM users WHERE email = 'rep@example.test'")).scalar() == "contributor"
        assert not set(inspect(migrated_engine).get_table_names()) & {"stories", "story_scripts", "story_reviews"}
    finally:
        command.upgrade(cfg, "head")
    with migrated_engine.begin() as conn:
        conn.execute(text("INSERT INTO users (email, display_name, role) VALUES ('rep2@example.test', 'Rep', 'reporter')"))
        conn.execute(text("TRUNCATE users CASCADE"))
