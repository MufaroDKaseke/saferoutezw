"""Phone subscriptions: verification, consent, privacy-safe responses and abuse limits (mock provider)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text

from app.models import AlertSubscriber, SubscriptionChallenge, SubscriptionConsent
from app.services.notifications import get_notification_provider
from public_helpers import configure  # noqa: F401

pytestmark = pytest.mark.usefixtures("migrated_engine")

S = "/api/v1/public/subscriptions"
PHONE = "+263771234567"


def body(**over):
    data = {
        "phone": "077 123 4567", "country_code": "+263", "channel": "sms", "all_zimbabwe": False,
        "provinces": ["Harare"], "corridors": [], "consent_accepted": True, "consent_version": "2026-11-v1",
    }
    data.update(over)
    return data


def code_for(settings, phone=PHONE, channel="sms"):
    return get_notification_provider(settings, channel).last_code_for(phone)


def subscribe_and_verify(client, settings, **over):
    assert client.post(S, json=body(**over)).status_code == 202
    r = client.post(f"{S}/verify", json={"phone": PHONE, "code": code_for(settings)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['management_token']}"}


def test_invalid_phone_numbers_are_rejected(client, configure):
    for bad in ("abc", "12", "+263 1"):
        r = client.post(S, json=body(phone=bad))
        assert r.status_code == 422  # rejected by schema or by the phone parser
    r = client.post(S, json=body(phone="12345678"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_PHONE"


def test_a_typed_number_is_not_active_until_verified(client, session, configure):
    assert client.post(S, json=body()).status_code == 202
    subscriber = session.scalar(select(AlertSubscriber))
    assert subscriber.status == "pending" and subscriber.verified_at is None
    assert PHONE not in subscriber.phone_ciphertext and PHONE not in subscriber.phone_digest
    assert session.scalar(select(SubscriptionConsent)).consent_text_version == "2026-11-v1"
    stored = session.execute(text("SELECT code_hash FROM subscription_challenges")).scalar()
    assert stored and len(stored) == 64  # hashed, never the six digits


def test_consent_is_required(client, configure):
    for over in ({"consent_accepted": False}, {"consent_version": "old"}):
        r = client.post(S, json=body(**over))
        assert r.status_code == 422 and r.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_verification_activates_and_issues_a_management_token(client, session, configure):
    settings = configure()
    headers = subscribe_and_verify(client, settings)
    assert session.scalar(select(AlertSubscriber)).status == "active"
    prefs = client.get(f"{S}/preferences", headers=headers).json()
    assert prefs["provinces"] == ["Harare"] and prefs["channel"] == "sms"
    kinds = [m.kind for m in get_notification_provider(settings, "sms").messages]
    assert kinds == ["verification", "optin"]


def test_wrong_and_expired_codes_do_not_activate(client, session, configure):
    settings = configure()
    client.post(S, json=body())
    real = code_for(settings)
    wrong = "000000" if real != "000000" else "111111"
    r = client.post(f"{S}/verify", json={"phone": PHONE, "code": wrong})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_CODE"
    session.execute(
        text("UPDATE subscription_challenges SET expires_at = :t"), {"t": datetime.now(UTC) - timedelta(minutes=1)}
    )
    session.commit()
    assert client.post(f"{S}/verify", json={"phone": PHONE, "code": real}).status_code == 400
    assert session.scalar(select(AlertSubscriber)).status == "pending"


def test_attempt_limit_locks_the_code(client, session, configure):
    settings = configure(otp_max_attempts=3)
    client.post(S, json=body())
    real = code_for(settings)
    wrong = "000000" if real != "000000" else "111111"
    for _ in range(3):
        assert client.post(f"{S}/verify", json={"phone": PHONE, "code": wrong}).status_code == 400
    assert client.post(f"{S}/verify", json={"phone": PHONE, "code": real}).status_code == 400
    assert session.scalar(select(AlertSubscriber)).status == "pending"


def test_resend_cooldown_and_hourly_cap(client, session, configure):
    settings = configure(otp_resend_cooldown_seconds=60)
    client.post(S, json=body())
    client.post(f"{S}/resend-verification", json={"phone": PHONE})
    assert len(get_notification_provider(settings, "sms").messages) == 1  # cooldown: nothing new sent
    assert session.scalar(select(SubscriptionChallenge.id).limit(2)) is not None


def test_responses_do_not_reveal_whether_a_number_exists(client, configure):
    settings = configure()
    first = client.post(S, json=body())
    subscribe_and_verify(client, settings)  # now active
    again = client.post(S, json=body())
    unknown = client.post(f"{S}/resend-verification", json={"phone": "+263772223333"})
    known = client.post(f"{S}/resend-verification", json={"phone": PHONE})
    assert first.status_code == again.status_code == unknown.status_code == known.status_code == 202
    assert first.json() == again.json() == unknown.json() == known.json()


def test_duplicate_registration_keeps_one_subscriber(client, session, configure):
    client.post(S, json=body())
    client.post(S, json=body(provinces=["Midlands"]))
    assert len(session.scalars(select(AlertSubscriber)).all()) == 1


def test_preferences_need_the_token_and_can_be_updated(client, configure):
    settings = configure()
    assert client.get(f"{S}/preferences").status_code == 401
    assert client.get(f"{S}/preferences", headers={"Authorization": "Bearer nope"}).status_code == 401
    headers = subscribe_and_verify(client, settings)
    r = client.patch(
        f"{S}/preferences", headers=headers,
        json={"all_zimbabwe": False, "provinces": ["Midlands", "Masvingo"], "corridors": ["A3 Harare-Mutare"]},
    )
    assert r.status_code == 200 and r.json()["provinces"] == ["Midlands", "Masvingo"]
    bad = client.patch(f"{S}/preferences", headers=headers, json={"all_zimbabwe": False, "provinces": [], "corridors": []})
    assert bad.status_code == 422


def test_unsubscribe_revokes_the_subscription_and_token(client, session, configure):
    settings = configure()
    headers = subscribe_and_verify(client, settings)
    assert client.post(f"{S}/unsubscribe", headers=headers).status_code == 200
    subscriber = session.scalar(select(AlertSubscriber))
    assert subscriber.status == "unsubscribed" and subscriber.unsubscribed_at
    assert session.scalar(select(SubscriptionConsent)).withdrawn_at is not None
    assert client.get(f"{S}/preferences", headers=headers).status_code == 401


def test_resubscribing_after_unsubscribe_needs_fresh_consent_and_verification(client, session, configure):
    settings = configure()
    headers = subscribe_and_verify(client, settings)
    client.post(f"{S}/unsubscribe", headers=headers)
    client.post(S, json=body())
    assert session.scalar(select(AlertSubscriber)).status == "pending"
    assert len(session.scalars(select(SubscriptionConsent)).all()) == 2


def test_subscription_endpoints_are_rate_limited(client, configure):
    configure(public_write_rate_limit_per_minute=2)
    assert client.post(S, json=body()).status_code == 202
    assert client.post(S, json=body()).status_code == 202
    assert client.post(S, json=body()).status_code == 429


def test_options_expose_no_subscriber_data(client, configure):
    data = client.get(f"{S}/options").json()
    assert data["default_country_code"] == "+263" and len(data["provinces"]) == 10
    assert data["messaging_mode"] == "mock"


def test_fixed_code_activates_without_sending_a_verification_message(client, session, configure):
    settings = configure(subscriber_fixed_code="000000")
    r = client.post(S, json=body())
    assert r.status_code == 202 and "000000" in r.json()["message"]
    assert get_notification_provider(settings, "sms").messages == []  # no code was sent
    assert client.post(f"{S}/verify", json={"phone": PHONE, "code": "123456"}).status_code == 400
    ok = client.post(f"{S}/verify", json={"phone": PHONE, "code": "000000"})
    assert ok.status_code == 200
    assert session.scalar(select(AlertSubscriber)).status == "active"
