"""Menu, global commands, expiry, ordering and idempotent replies."""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import WhatsAppConversation, WhatsAppOutbound
from whatsapp_helpers import Chat

pytestmark = pytest.mark.usefixtures("migrated_engine")

WELCOME = "Welcome to SafeRouteZW 🇿🇼\n\n1. Report a road incident\n2. Road alerts\n3. Check a route\n\nReply with 1, 2 or 3."


def test_first_message_shows_the_three_option_menu_with_buttons(session):
    chat = Chat(session)
    assert chat.say("hello") == [WELCOME]
    sent = chat.client.sent[0]
    assert sent.kind == "buttons" and sent.choices == ("1", "2", "3")


@pytest.mark.parametrize("number,expected", [("1", "Where did it happen"), ("2", "Road alerts"), ("3", "Where are you starting")])
def test_numeric_replies_work_as_a_fallback_for_buttons(session, number, expected):
    chat = Chat(session)
    chat.say("hi")
    assert expected in chat.say(number)[0]


def test_tapping_a_button_equals_typing_the_number(session):
    chat = Chat(session)
    chat.say("hi")
    assert "Where did it happen" in chat.tap("1", "Report incident")[0]


def test_unrecognised_menu_reply_shows_the_menu_again(session):
    chat = Chat(session)
    chat.say("hi")
    reply = chat.say("banana")[0]
    assert "Please reply with 1, 2 or 3." in reply and "Welcome to SafeRouteZW" in reply


def test_menu_command_returns_from_any_step_and_erases_the_draft(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Harare road")
    assert "Welcome to SafeRouteZW" in chat.say("menu")[0]
    conv = session.scalar(select(WhatsAppConversation))
    assert conv.flow == "menu" and conv.data == {}


def test_cancel_discards_the_draft_and_saves_nothing(session):
    from app.models import SourceItem

    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Harare road"), chat.say("A truck overturned here")
    assert "Cancelled. Nothing was saved" in chat.say("CANCEL")[0]
    assert session.scalar(select(func.count()).select_from(SourceItem)) == 0
    assert session.scalar(select(WhatsAppConversation)).data == {}


def test_back_goes_to_the_previous_step_and_then_the_menu(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Harare road")  # now asking "what"
    assert "Where did it happen" in chat.say("back")[0]
    assert "Welcome to SafeRouteZW" in chat.say("back")[0]


def test_help_explains_and_repeats_the_current_question(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1")
    replies = chat.say("help")
    assert "Commands: MENU" in replies[0] and "Where did it happen" in replies[1]


def test_help_adds_no_extra_business_function(session):
    chat = Chat(session)
    chat.say("hi")
    text = chat.say("help")[0].lower()
    assert "report" in text and "alerts" in text and "route" in text


def test_expired_conversation_resets_to_the_menu_and_erases_the_draft(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Harare road")
    chat.now += timedelta(minutes=chat.settings.whatsapp_session_ttl_minutes + 1)
    reply = chat.say("A truck overturned")[0]
    assert "timed out" in reply and "Welcome to SafeRouteZW" in reply
    conv = session.scalar(select(WhatsAppConversation))
    assert conv.flow == "menu" and conv.data == {}


def test_activity_extends_the_session(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1")
    first = session.scalar(select(WhatsAppConversation.expires_at))
    chat.now += timedelta(minutes=10)
    chat.say("Harare road")
    assert session.scalar(select(WhatsAppConversation.expires_at)) > first


def test_conversations_are_separate_per_sender(session):
    a, b = Chat(session, wa_id="263771000001"), Chat(session, wa_id="263771000002")
    a.say("hi"), a.say("1")
    b.say("hi")
    assert "Welcome to SafeRouteZW" in b.say("banana")[0]
    assert "What happened" in a.say("Harare road")[0]


def test_out_of_order_input_gets_a_reprompt_not_a_crash(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("3")  # asking for the origin
    assert "Where are you starting" in chat.tap("1", "Happening now")[0] or "Please type a place" in chat.last
    # A location pin in a text-only step, a photo mid-flow and a stale list row are all survivable.
    chat.say("menu"), chat.say("1")
    assert "Please type a road name" in chat.say("x")[0]  # too short: asked again
    assert "Photos can't be added" in chat.photo()[0]
    chat.say("Harare road")
    assert "Please describe what happened" in chat.pin(-17.8, 31.0)[0]  # a pin where text is expected
    chat.say("menu"), chat.say("3")
    assert chat.tap("c:destination:1")  # stale row id while asking origin: answered, not raised


def test_reprocessing_a_message_does_not_send_the_reply_twice(session):
    chat = Chat(session)
    chat.say("hi", wamid="wamid.SAME")
    before = len(chat.client.sent)
    assert chat.say("hi", wamid="wamid.SAME") == []  # duplicate delivery is ignored
    assert len(chat.client.sent) == before
    assert session.scalar(select(func.count()).select_from(WhatsAppOutbound)) == 1
