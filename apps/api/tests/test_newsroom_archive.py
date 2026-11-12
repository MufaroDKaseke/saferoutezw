"""NUST FM archive: stories that went to air and the bulletin revisions that aired them, searchable by everyone,
with the version that was read, the decisions behind it, and follow-up links between stories."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from newsroom_helpers import (  # noqa: F401  (newsroom_client and room are fixtures)
    B,
    N,
    S,
    aired,
    approved_story,
    live_bulletin,
    make_article,
    make_bulletin,
    make_staff,
    newsroom_client,
    put_items,
    revision_action,
    room,
    words,
)
from newsroom_helpers import classification

pytestmark = pytest.mark.usefixtures("migrated_engine")

A = f"{N}/archive"


def ids(response):
    return [i["id"] for i in response.json()["items"]]


def archive(room, **params):
    return room.get(A, params=params)


# ---- access and mode --------------------------------------------------------------------------------------------


def test_archive_routes_do_not_exist_in_road_safety_mode(client):
    for path in (A, f"{A}/bulletins", f"{A}/stories/{uuid.uuid4()}", f"{A}/bulletins/{uuid.uuid4()}/revisions/1"):
        assert client.get(path).status_code == 404


def test_anonymous_users_are_turned_away(newsroom_client):
    for path in (A, f"{A}/bulletins"):
        assert newsroom_client.get(path).status_code == 401


@pytest.mark.parametrize("role", ["reporter", "analyst", "editor", "admin"])
def test_everyone_signed_in_can_read_the_archive_including_other_reporters_stories(room, session, role):
    story_id, _ = aired(room, session)  # the first reporter's story
    room.as_(make_staff(session, role))
    assert ids(archive(room)) == [story_id]
    assert room.get(f"{A}/stories/{story_id}").status_code == 200
    assert room.get(f"{A}/bulletins").json()["total"] == 1


def test_the_archive_is_read_only(room, session):
    story_id, bulletin = aired(room, session)
    room.as_(room.ep)
    assert room.post(A, {}).status_code == 405
    assert room.client.put(f"{A}/stories/{story_id}", json={}, headers=room.headers).status_code == 405
    assert room.client.delete(f"{A}/stories/{story_id}", headers=room.headers).status_code == 405


# ---- what is in the archive ---------------------------------------------------------------------------------------


def test_only_stories_that_went_to_air_are_archived(room, session):
    unaired_story, _ = approved_story(room, session)  # approved, never in a bulletin
    live, live_ids = live_bulletin(room, session, stories=1)  # in a live bulletin, not broadcast yet
    aired_story, _ = aired(room, session, name="Aired one")
    room.as_(room.analyst)
    assert ids(archive(room)) == [aired_story]
    assert room.get(f"{A}/stories/{unaired_story}").json()["error"]["code"] == "ARCHIVE_STORY_NOT_FOUND"
    assert room.get(f"{A}/stories/{live_ids[0]}").status_code == 404
    assert room.get(f"{A}/stories/{uuid.uuid4()}").status_code == 404
    assert room.get(f"{A}/bulletins").json()["total"] == 1  # the live-but-unaired bulletin is not an aired revision
    assert room.get(f"{A}/bulletins/{live['id']}/revisions/1").status_code == 404


def test_an_archived_story_shows_what_aired_where_and_who_wrote_it(room, session):
    story_id, bulletin = aired(
        room, session, name="Evening News", script_body="The council approved its 2027 budget on Tuesday. " + words(60),
        title_redacted="Council budget", canonical_url="https://herald.example/budget",
        reply=classification(primary_category="politics_governance"),
    )
    room.as_(room.analyst)
    entry = archive(room).json()["items"][0]
    assert entry["id"] == story_id and entry["title"] == "Council budget" and entry["headline"] == "Council approves budget"
    assert entry["excerpt"].startswith("The council approved its 2027 budget on Tuesday.") and entry["excerpt"].endswith("…")
    assert entry["category"] == "politics_governance" and entry["category_label"] == "Politics & Governance"
    assert entry["reporter"]["id"] == str(room.reporter.id)
    assert entry["publisher"] and entry["source_url"] == "https://herald.example/budget"
    assert entry["aired_at"] and entry["last_aired_at"] == entry["aired_at"]
    assert [(b["name"], b["revision_number"]) for b in entry["bulletins"]] == [("Evening News", 1)]
    assert entry["follows"] is None and entry["follow_up_count"] == 0


def test_the_story_detail_keeps_the_aired_script_the_version_history_and_the_decisions(room, session):
    story_id, _ = aired(room, session, script_body="The aired text.")
    room.as_(room.reporter)
    detail = room.get(f"{A}/stories/{story_id}").json()
    (script,) = detail["scripts"]
    assert script["version_number"] == 1 and script["body"] == "The aired text." and script["origin"] == "human"
    assert script["aired_in"][0]["name"] == "6pm News" and script["created_by"]["id"] == str(room.reporter.id)
    (version,) = detail["versions"]
    assert version["version_number"] == 1 and version["approved"] is True and version["aired"] is True
    (review,) = detail["reviews"]
    assert review["decision"] == "approved" and review["script_version"] == 1 and review["reviewer"]["id"] == str(room.ep.id)
    assert review["self_approved"] is False
    assert detail["source_item_id"] and detail["followed_by"] == []


def test_a_story_rewritten_before_it_aired_is_archived_with_the_version_that_was_read(room, session):
    bulletin = make_bulletin(room)
    story_id, _ = approved_story(room, session, script_body="The approved text that will air.")
    room.as_(room.ep)
    put_items(room, bulletin["id"], 1, [{"story_id": story_id}])
    revision_action(room, bulletin["id"], 1, "submit")
    revision_action(room, bulletin["id"], 1, "approve")
    room.as_(room.reporter)
    room.script(story_id, headline="Rewritten headline", body="An unapproved rewrite nobody has checked.", base=1)
    room.as_(room.ep)
    room.post(f"{B}/{bulletin['id']}/broadcast")

    room.as_(room.analyst)
    entry = archive(room).json()["items"][0]
    assert entry["headline"] == "Council approves budget" and entry["excerpt"] == "The approved text that will air."
    detail = room.get(f"{A}/stories/{story_id}").json()
    assert [s["body"] for s in detail["scripts"]] == ["The approved text that will air."]  # only what aired carries text
    assert [(v["version_number"], v["approved"], v["aired"]) for v in detail["versions"]] == [(1, True, True), (2, False, False)]
    assert "unapproved rewrite" not in str(detail["scripts"]) and "unapproved rewrite" not in str(entry)


def test_a_story_that_aired_in_two_bulletins_lists_both(room, session):
    first_story, first = aired(room, session, name="Morning")
    second = make_bulletin(room, name="Noon")
    room.as_(room.ep)
    put_items(room, second["id"], 1, [{"story_id": first_story}])
    revision_action(room, second["id"], 1, "submit")
    revision_action(room, second["id"], 1, "approve")
    room.post(f"{B}/{second['id']}/broadcast")
    entry = archive(room).json()["items"][0]
    assert [b["name"] for b in entry["bulletins"]] == ["Morning", "Noon"]
    assert datetime.fromisoformat(entry["last_aired_at"]) > datetime.fromisoformat(entry["aired_at"])
    assert archive(room).json()["total"] == 1  # one story, however often it aired


# ---- search -----------------------------------------------------------------------------------------------------


def test_search_covers_the_title_and_the_headline_and_text_of_what_aired(room, session):
    a, _ = aired(room, session, name="A", title_redacted="Zebra crossing opens", script_body="Plain text.")
    b, _ = aired(room, session, name="B", title_redacted="Dam levels", script_body="The okapi was seen near the dam.")
    c, _ = aired(room, session, name="C", title_redacted="Power cuts", script_body="Plain.", headline="Pangolin outage")
    room.as_(room.analyst)
    for term, expected in (("zebra", a), ("okapi", b), ("pangolin", c), ("OKAPI", b)):
        assert ids(archive(room, q=term)) == [expected], term
    assert archive(room, q="100%_").json()["total"] == 0  # wildcards are escaped
    assert archive(room, q="nothing like this").json()["total"] == 0
    assert archive(room).json()["total"] == 3


def test_unaired_draft_text_is_never_searchable(room, session):
    story_id, _ = aired(room, session, script_body="The aired words.")
    other = room.take(room.other, make_article(session, title_redacted="Unrelated"))
    room.verify(other)
    room.script(other, body="A xylophone appears only in this unaired draft.")
    room.as_(room.analyst)
    assert archive(room, q="xylophone").json()["total"] == 0


def test_the_archive_filters_by_date_and_category(room, session):
    sport, _ = aired(room, session, name="Sport", reply=classification(primary_category="sports", secondary_category="education"))
    politics, _ = aired(room, session, name="Politics", reply=classification(primary_category="politics_governance"))
    room.as_(room.analyst)
    assert set(ids(archive(room, category="sports"))) == {sport}
    assert set(ids(archive(room, category="education"))) == {sport}  # secondary category counts too
    assert set(ids(archive(room, category="politics_governance"))) == {politics}
    assert archive(room, category="not_a_category").status_code == 422
    now = datetime.now(UTC)
    day = timedelta(days=1)
    assert archive(room, aired_from=(now - day).isoformat(), aired_to=(now + day).isoformat()).json()["total"] == 2
    assert archive(room, aired_from=(now + day).isoformat()).json()["total"] == 0
    assert archive(room, aired_to=(now - day).isoformat()).json()["total"] == 0


def test_newest_first_and_paginated(room, session):
    names = [aired(room, session, name=f"Bulletin {i}", title_redacted=f"Story {i}")[0] for i in range(3)]
    room.as_(room.analyst)
    assert ids(archive(room)) == list(reversed(names))
    page = archive(room, page_size=2, page=2).json()
    assert page["total"] == 3 and ids(archive(room, page_size=2, page=2)) == [names[0]]
    assert page["page"] == 2 and page["page_size"] == 2


# ---- follow-ups ---------------------------------------------------------------------------------------------------


def follow_up(room, session, earlier_id, title="Follow-up: council budget", air=True):
    """A reporter starts a follow-up of ``earlier_id`` and, optionally, it goes to air. Returns its id."""
    room.as_(room.reporter)
    created = room.post(S, {"title": title, "follows_story_id": earlier_id})
    assert created.status_code == 201, created.text
    story_id = created.json()["id"]
    if not air:
        return story_id
    room.verify(story_id)
    room.script(story_id, headline="Council responds")
    room.submit(story_id)
    room.as_(room.ep)
    room.review(story_id, 1)
    bulletin = make_bulletin(room, name=f"Bulletin for {title}")
    put_items(room, bulletin["id"], 1, [{"story_id": story_id}])
    revision_action(room, bulletin["id"], 1, "submit")
    revision_action(room, bulletin["id"], 1, "approve")
    room.post(f"{B}/{bulletin['id']}/broadcast")
    return story_id


def test_follow_ups_link_both_ways_once_they_have_aired(room, session):
    original, _ = aired(room, session, title_redacted="Council budget")
    later = follow_up(room, session, original)
    room.as_(room.analyst)
    entries = {e["id"]: e for e in archive(room).json()["items"]}
    assert entries[original]["follow_up_count"] == 1 and entries[original]["follows"] is None
    assert entries[later]["follows"]["id"] == original and entries[later]["follows"]["title"] == "Council budget"
    assert room.get(f"{A}/stories/{original}").json()["followed_by"] == [
        {"id": later, "title": "Follow-up: council budget", "aired_at": entries[later]["aired_at"]}
    ]
    assert room.get(f"{A}/stories/{later}").json()["follows"]["id"] == original


def test_a_follow_up_that_has_not_aired_is_not_shown(room, session):
    original, _ = aired(room, session)
    pending = follow_up(room, session, original, title="Still being written", air=False)
    room.as_(room.analyst)
    assert archive(room).json()["items"][0]["follow_up_count"] == 0
    assert room.get(f"{A}/stories/{original}").json()["followed_by"] == []
    assert room.get(f"{A}/stories/{pending}").status_code == 404


def test_a_follow_up_of_a_story_that_never_aired_does_not_point_at_it(room, session):
    never_aired = room.take(room.reporter, title="Never aired")
    later = follow_up(room, session, never_aired, title="Follows an unaired story")
    room.as_(room.analyst)
    assert room.get(f"{A}/stories/{later}").json()["follows"] is None  # an unaired story is not in the archive to link to


# ---- aired bulletin revisions -------------------------------------------------------------------------------------


def test_aired_revisions_are_listed_with_their_running_time_and_who_aired_them(room, session):
    story_id, bulletin = aired(room, session, name="6pm News")
    room.as_(room.analyst)
    (entry,) = room.get(f"{A}/bulletins").json()["items"]
    assert entry["id"] == bulletin["id"] and entry["name"] == "6pm News" and entry["revision_number"] == 1
    assert entry["story_count"] == 1 and entry["total_seconds"] == 30 and entry["aired_by"]["id"] == str(room.ep.id)
    assert entry["aired_at"] and entry["scheduled_for"]


def test_each_aired_revision_keeps_exactly_what_was_read(room, session):
    story_id, bulletin = aired(room, session, name="6pm News", script_body="Revision one text.")
    bid = bulletin["id"]
    second_story, _ = approved_story(room, session, script_body="Revision two extra story.")
    room.as_(room.ep)
    room.post(f"{B}/{bid}/revisions")
    put_items(room, bid, 2, [{"story_id": story_id}, {"story_id": second_story, "note": "Play the jingle"}])
    revision_action(room, bid, 2, "submit")
    revision_action(room, bid, 2, "approve")
    room.post(f"{B}/{bid}/broadcast")

    room.as_(room.analyst)
    listed = room.get(f"{A}/bulletins").json()
    assert listed["total"] == 2 and [i["revision_number"] for i in listed["items"]] == [2, 1]  # both aired, newest first
    one = room.get(f"{A}/bulletins/{bid}/revisions/1").json()
    two = room.get(f"{A}/bulletins/{bid}/revisions/2").json()
    assert [i["body"] for i in one["items"]] == ["Revision one text."]
    assert [i["body"] for i in two["items"]] == ["Revision one text.", "Revision two extra story."]
    assert two["items"][1]["note"] == "Play the jingle" and two["items"][0]["story_id"] == story_id
    assert one["approved_by"]["id"] == str(room.ep.id) and one["approved_at"] and one["target_seconds"] == 300
    assert one["revision_number"] == 1 and two["total_seconds"] == one["total_seconds"] + 2


def test_a_revision_that_never_aired_is_not_in_the_archive(room, session):
    story_id, bulletin = aired(room, session)
    bid = bulletin["id"]
    room.as_(room.ep)
    room.post(f"{B}/{bid}/revisions")  # revision 2: a draft
    room.as_(room.analyst)
    assert room.get(f"{A}/bulletins/{bid}/revisions/2").json()["error"]["code"] == "ARCHIVE_BULLETIN_NOT_FOUND"
    assert room.get(f"{A}/bulletins").json()["total"] == 1


def test_aired_bulletins_can_be_searched_by_name_story_and_date(room, session):
    aired(room, session, name="Morning briefing", title_redacted="Water shedding")
    aired(room, session, name="Evening sport", title_redacted="Cup final")
    room.as_(room.analyst)
    names = lambda **p: sorted(i["name"] for i in room.get(f"{A}/bulletins", params=p).json()["items"])  # noqa: E731
    assert names(q="morning") == ["Morning briefing"]
    assert names(q="cup final") == ["Evening sport"]  # by the title of a story in it
    assert names(q="100%_") == []
    now = datetime.now(UTC)
    assert len(names(aired_from=(now - timedelta(days=1)).isoformat())) == 2
    assert names(aired_from=(now + timedelta(days=1)).isoformat()) == []


# ---- dashboard counters ----------------------------------------------------------------------------------------------


def workflow(room):
    room.as_(room.analyst)
    return room.get(f"{N}/summary").json()["workflow"]


def test_the_dashboard_counts_stories_awaiting_approval_and_the_next_bulletin(room, session):
    assert workflow(room) == {"stories_awaiting_approval": 0, "stories_in_progress": 0, "bulletins_awaiting_approval": 0, "next_bulletin": None}
    waiting = room.take(room.reporter, make_article(session))
    room.verify(waiting)
    room.script(waiting)
    room.submit(waiting)
    room.take(room.reporter, make_article(session))  # just assigned
    summary = workflow(room)
    assert summary["stories_awaiting_approval"] == 1 and summary["stories_in_progress"] == 2
    # bulletins: the soonest one that has not aired
    later = make_bulletin(room, name="Later", scheduled_for="2099-06-01T18:00:00Z")
    soon = make_bulletin(room, name="Sooner", scheduled_for="2099-06-01T06:00:00Z")
    assert workflow(room)["next_bulletin"]["name"] == "Sooner"
    story, _ = approved_story(room, session)
    room.as_(room.ep)
    put_items(room, soon["id"], 1, [{"story_id": story}])
    revision_action(room, soon["id"], 1, "submit")
    assert workflow(room)["bulletins_awaiting_approval"] == 1  # (this call signs in as the analyst)
    room.as_(room.ep)
    assert revision_action(room, soon["id"], 1, "approve").status_code == 200
    assert room.post(f"{B}/{soon['id']}/broadcast").status_code == 200
    after = workflow(room)
    assert after["next_bulletin"]["name"] == "Later" and after["bulletins_awaiting_approval"] == 0
    assert after["stories_in_progress"] == 2  # the aired story left the count: two others are still open


def test_a_bulletin_that_is_a_little_late_is_still_the_next_one_but_an_old_one_is_not(room, session):
    make_bulletin(room, name="Long gone", scheduled_for=(datetime.now(UTC) - timedelta(days=3)).isoformat())
    assert workflow(room)["next_bulletin"] is None
    make_bulletin(room, name="Running late", scheduled_for=(datetime.now(UTC) - timedelta(minutes=20)).isoformat())
    assert workflow(room)["next_bulletin"]["name"] == "Running late"
