"""Function 2: road alert subscriptions through the existing subscriber domain. Mock providers only."""

import pytest
from sqlalchemy import func, select

from app.models import AlertSubscriber, SubscriberDelivery, SubscriptionConsent, SubscriptionPreference
from app.services import alert_notifications as notifications
from app.services.notifications import get_notification_provider, reset_mock_providers
from public_helpers import make_published_alert
from whatsapp_helpers import Chat

pytestmark = pytest.mark.usefixtures("migrated_engine")

E164 = "+263771234567"


@pytest.fixture(autouse=True)
def fresh_providers():
    reset_mock_providers()
    yield
    reset_mock_providers()


def code_sent(chat: Chat) -> str:
    code = get_notification_provider(chat.settings, "whatsapp").last_code_for(E164)
    assert code, "no verification code was sent over WhatsApp"
    return code


def start_signup(chat: Chat, areas="Mashonaland East") -> list[str]:
    chat.say("hi"), chat.say("2"), chat.say("1")
    return chat.say(areas)  # the consent prompt


def subscribe(chat: Chat, areas="Mashonaland East") -> list[str]:
    start_signup(chat, areas)
    chat.say("1")  # I agree
    return chat.say(code_sent(chat))


def subscriber(session) -> AlertSubscriber | None:
    return session.scalar(select(AlertSubscriber))


def alerts_in(provider):
    return [m for m in provider.messages if m.kind == "alert"]


def deliver(session, chat):
    provider = get_notification_provider(chat.settings, "whatsapp")
    return notifications.run_once(session, chat.settings, provider_for=lambda c: provider, channel="whatsapp"), provider


def test_alerts_menu_offers_subscribe_manage_unsubscribe(session):
    chat = Chat(session)
    chat.say("hi")
    reply = chat.say("2")[0]
    assert "1. Subscribe" in reply and "2. Manage preferences" in reply and "3. Unsubscribe" in reply
    assert chat.client.sent[-1].choices == ("1", "2", "3")


def test_consent_prompt_explains_the_messages_and_asks_explicitly(session):
    chat = Chat(session)
    prompt = start_signup(chat)[0]
    assert "Mashonaland East" in prompt
    assert "reviewed" in prompt and "published" in prompt
    assert "I agree to receive SafeRouteZW road safety alerts on this number by WhatsApp" in prompt
    assert subscriber(session) is None  # nothing is recorded before they agree


def test_full_opt_in_activates_only_after_consent_and_the_code(session):
    chat = Chat(session)
    start_signup(chat)
    otp_prompt = chat.say("1")[0]
    assert "not subscribed until you do" in otp_prompt
    sub = subscriber(session)
    assert sub.status == "pending" and sub.channel == "whatsapp" and sub.verified_at is None

    reply = chat.say(code_sent(chat))[0]
    session.expire_all()
    sub = subscriber(session)
    assert sub.status == "active" and sub.verified_at is not None
    assert "You're subscribed" in reply and "Mashonaland East" in reply
    prefs = session.scalar(select(SubscriptionPreference))
    assert prefs.provinces == ["Mashonaland East"] and not prefs.all_zimbabwe
    consent = session.scalar(select(SubscriptionConsent))
    assert consent.channel == "whatsapp" and consent.withdrawn_at is None


def test_declining_consent_creates_no_subscriber(session):
    chat = Chat(session)
    start_signup(chat)
    assert "not been subscribed" in chat.say("2")[0]
    assert subscriber(session) is None


def test_a_wrong_code_leaves_the_number_unverified_and_it_gets_no_alerts(session):
    chat = Chat(session)
    start_signup(chat), chat.say("1")
    wrong = "000000" if code_sent(chat) != "000000" else "111111"
    assert "isn't right" in chat.say(wrong)[0]
    session.expire_all()
    assert subscriber(session).status == "pending"
    make_published_alert(session)
    summary, provider = deliver(session, chat)
    assert summary.queued == 0 and summary.sent == 0 and alerts_in(provider) == []


def test_unverified_pending_number_cannot_receive_alerts_even_with_consent(session):
    chat = Chat(session)
    start_signup(chat), chat.say("1")  # consent given, code never entered
    make_published_alert(session)
    summary, provider = deliver(session, chat)
    assert (summary.queued, summary.sent) == (0, 0)
    assert session.scalar(select(func.count()).select_from(SubscriberDelivery)) == 0


def test_using_the_bot_or_reporting_does_not_subscribe_anyone(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("1"), chat.say("Harare road"), chat.say("A truck overturned here today"), chat.say("1"), chat.say("1")
    assert subscriber(session) is None
    make_published_alert(session)
    summary, _ = deliver(session, chat)
    assert summary.sent == 0


def test_unrecognised_areas_are_rejected_with_the_offending_words(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("2"), chat.say("1")
    reply = chat.say("Narnia, Harare")[0]
    assert "didn't recognise: Narnia" in reply
    assert "Which areas" in chat.last


def test_all_zimbabwe_and_a_road_corridor_are_accepted(session):
    chat = Chat(session)
    assert "All Zimbabwe" in start_signup(chat, "ALL")[0]
    chat.say("menu"), chat.say("2"), chat.say("1")
    assert "A3 Harare-Mutare" in chat.say("Harare, A3 Harare-Mutare")[0]


def test_published_alert_reaches_only_the_verified_whatsapp_subscriber_once(session):
    chat = Chat(session)
    subscribe(chat)
    make_published_alert(session, province="Mashonaland East")
    first, provider = deliver(session, chat)
    assert (first.queued, first.sent) == (1, 1)
    [alert_message] = alerts_in(provider)
    assert "SafeRouteZW" in alert_message.body and "Reply STOP" in alert_message.body
    assert "/public/alerts/" in alert_message.body
    again, provider = deliver(session, chat)
    assert (again.queued, again.sent) == (0, 0)  # no duplicate notification
    assert session.scalar(select(func.count()).select_from(SubscriberDelivery)) == 1


def test_alerts_outside_the_chosen_area_are_not_sent(session):
    chat = Chat(session)
    subscribe(chat, "Bulawayo")
    make_published_alert(session, province="Mashonaland East")
    summary, _ = deliver(session, chat)
    assert summary.sent == 0


def test_unpublished_alerts_are_never_sent(session):
    from sqlalchemy import update
    from app.models import PublicAlert

    chat = Chat(session)
    subscribe(chat)
    alert, *_ = make_published_alert(session)
    session.execute(update(PublicAlert).where(PublicAlert.id == alert.id).values(status="withdrawn"))
    session.commit()
    summary, provider = deliver(session, chat)
    assert summary.sent == 0 and alerts_in(provider) == []


def test_stop_unsubscribes_withdraws_consent_and_stops_alerts(session):
    chat = Chat(session)
    subscribe(chat)
    assert "unsubscribed" in chat.say("stop")[0]
    session.expire_all()
    assert subscriber(session).status == "unsubscribed"
    assert session.scalar(select(SubscriptionConsent)).withdrawn_at is not None
    make_published_alert(session)
    summary, _ = deliver(session, chat)
    assert summary.sent == 0


def test_stop_works_in_the_middle_of_another_flow(session):
    chat = Chat(session)
    subscribe(chat)
    chat.say("menu"), chat.say("1"), chat.say("Harare road")
    assert "unsubscribed" in chat.say("STOP")[0]
    session.expire_all()
    assert subscriber(session).status == "unsubscribed"


def test_stop_from_a_stranger_changes_nothing(session):
    chat = Chat(session)
    assert "aren't subscribed" in chat.say("stop")[0]
    assert subscriber(session) is None


def test_unsubscribe_option_in_the_menu(session):
    chat = Chat(session)
    subscribe(chat)
    chat.say("menu"), chat.say("2")
    assert "unsubscribed" in chat.say("3")[0]


def test_manage_preferences_changes_areas_without_new_consent(session):
    chat = Chat(session)
    subscribe(chat)
    chat.say("menu"), chat.say("2")
    assert "currently get alerts for: Mashonaland East" in chat.say("2")[0]
    assert "Updated" in chat.say("Harare, Bulawayo")[0]
    session.expire_all()
    assert set(session.scalar(select(SubscriptionPreference)).provinces) == {"Harare", "Bulawayo"}
    assert session.scalar(select(func.count()).select_from(SubscriptionConsent)) == 1


def test_manage_requires_an_active_subscription(session):
    chat = Chat(session)
    chat.say("hi"), chat.say("2")
    assert "not subscribed" in chat.say("2")[0]


def test_already_subscribed_is_told_so_instead_of_starting_again(session):
    chat = Chat(session)
    subscribe(chat)
    chat.say("menu"), chat.say("2")
    assert "already subscribed" in chat.say("1")[0]


def test_resubscribing_after_stop_needs_fresh_consent_and_code(session):
    chat = Chat(session)
    subscribe(chat)
    chat.say("stop")
    reset_mock_providers()
    chat.say("menu"), chat.say("2"), chat.say("1"), chat.say("Harare")
    chat.say("1")
    session.expire_all()
    assert subscriber(session).status == "pending"
    chat.say(code_sent(chat))
    session.expire_all()
    assert subscriber(session).status == "active"
