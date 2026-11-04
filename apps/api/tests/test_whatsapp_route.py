"""Function 3: route check. Replies carry only what the routing service and published alerts return."""

import re

import pytest
from sqlalchemy import update

from app.models import PublicAlert
from app.services.routing.mock import MockRoutingProvider
from public_helpers import PLACES, make_published_alert
from whatsapp_helpers import Chat, make_deps

pytestmark = pytest.mark.usefixtures("migrated_engine")

ON_ROUTE = dict(lat=-18.216, lng=31.6)  # on the straight Harare-Mutare mock line


def check(chat: Chat, origin="Harare", destination="Mutare") -> str:
    chat.say("hi"), chat.say("3"), chat.say(origin)
    return chat.say(destination)[0]


def expected_numbers(provider: MockRoutingProvider):
    result = provider.route([PLACES["harare"], PLACES["mutare"]], "drive")
    return result.distance_m, result.duration_s


def test_route_with_no_alerts_reports_real_distance_and_zero_alerts(session):
    chat = Chat(session)
    reply = check(chat)
    distance_m, duration_s = expected_numbers(MockRoutingProvider(PLACES))
    assert reply.startswith("SafeRouteZW — Route Check")
    assert "Harare → Mutare" in reply
    assert f"Distance: {round(distance_m / 1000)} km" in reply
    hours, minutes = divmod(round(duration_s / 60), 60)
    assert f"Estimated drive: {hours} h {minutes:02d} min" in reply and "no live traffic" in reply
    assert "Published road alerts: 0" in reply
    assert "No reported alerts does not guarantee the road is safe" in reply
    assert "View details: https://saferoute.example/public/routes?from=Harare&to=Mutare" in reply


def test_published_alerts_near_the_route_are_listed(session):
    make_published_alert(session, headline="Crash near Marondera", **ON_ROUTE)
    reply = check(Chat(session))
    assert "Published road alerts: 1" in reply and "Crash near Marondera" in reply


def test_unpublished_or_far_alerts_are_not_shown(session):
    alert, *_ = make_published_alert(session, headline="Withdrawn crash", **ON_ROUTE)
    session.execute(update(PublicAlert).where(PublicAlert.id == alert.id).values(status="withdrawn"))
    session.commit()
    make_published_alert(session, headline="Crash in Bulawayo", lat=-20.13, lng=28.62)
    reply = check(Chat(session))
    assert "Published road alerts: 0" in reply
    assert "Withdrawn crash" not in reply and "Bulawayo" not in reply


def test_only_the_most_relevant_few_alerts_are_shown_with_a_link_for_the_rest(session):
    for i in range(5):
        make_published_alert(session, headline=f"Crash number {i}", lat=-18.216 + i * 0.001, lng=31.6)
    reply = check(Chat(session))
    assert "Published road alerts: 5" in reply
    assert reply.count("• ") == 3 and "+ 2 more on the website" in reply
    assert len(reply) < 1200  # readable on a phone


def test_ambiguous_place_asks_the_user_to_choose_a_candidate(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3")
    prompt = chat.say("Chegutu")[0]
    assert "Several places match" in prompt and "1. Chegutu, Mashonaland West" in prompt
    assert chat.client.sent[-1].kind == "list"
    assert chat.client.sent[-1].choices == ("c:origin:1", "c:origin:2", "c:origin:0")
    assert "Where are you going" in chat.tap("c:origin:1")[0]
    reply = chat.say("Mutare")[0]
    assert "Chegutu → Mutare" in reply


def test_numeric_reply_selects_a_candidate_too(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3"), chat.say("Chegutu")
    assert "Where are you going" in chat.say("2")[0]


def test_stale_or_invalid_choices_are_not_accepted(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3"), chat.say("Chegutu")
    assert "Several places match" in chat.tap("c:destination:1")[0]  # a row from another question
    assert "Several places match" in " ".join(chat.say("9"))  # told to pick from the list, then shown it again
    assert "Several places match" in " ".join(chat.say("abc"))


def test_none_of_these_searches_again(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3"), chat.say("Chegutu")
    assert "Where are you starting" in chat.tap("c:origin:0")[0]


def test_unknown_place_is_reported_and_asked_again(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3")
    assert "couldn't find “Atlantis”" in chat.say("Atlantis")[0]
    assert "Where are you going" in chat.say("Harare")[0]  # the conversation carries on after a miss


def test_unknown_destination_never_produces_a_route(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3"), chat.say("Harare")
    reply = chat.say("Atlantis")[0]
    assert "couldn't find" in reply and "Distance" not in reply


def test_a_shared_location_pin_can_be_the_origin(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3")
    assert "Where are you going" in chat.pin(*PLACES["harare"])[0]
    assert "Shared location → Mutare" in chat.say("Mutare")[0]


def test_geocoder_outage_says_so_and_invents_nothing(session):
    chat = Chat(session, deps=make_deps(fail_geocoder=True))
    chat.say("hi"), chat.say("3")
    reply = chat.say("Harare")[0]
    assert "temporarily unavailable" in reply and "Distance" not in reply


def test_routing_outage_says_so_and_invents_nothing(session):
    chat = Chat(session, deps=make_deps(routing=MockRoutingProvider(PLACES, fail="unavailable")))
    reply = check(chat)
    assert "Route checking is temporarily unavailable" in reply
    assert not re.search(r"\d+ km|Estimated drive|Published road alerts", reply)


def test_after_a_result_the_user_is_back_at_the_menu(session):
    chat = Chat(session)
    check(chat)
    assert "Where did it happen" in chat.say("1")[0]
