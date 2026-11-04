"""Pure-logic tests that need no database."""

import pytest

from app.api.errors import ApiError
from app.api.rate_limit import check_rate_limit, reset_rate_limits
from app.repositories.public import make_summary_text
from app.schemas.public import PublicAlertDetail, PublicAlertSummary
from app.services import subscriptions as svc
from app.services.notifications.mock import MockNotificationProvider
from app.services.routing.base import RoutingError, RoutingUnavailable
from app.services.routing.geoapify import GeoapifyProvider
from app.services.routing.mock import MockRoutingProvider
from app.services.zimbabwe import detect_province, normalise_province
from public_helpers import PLACES, make_settings


def test_phone_numbers_are_normalised_to_e164():
    assert svc.normalise_phone("077 123 4567", "+263") == "+263771234567"
    assert svc.normalise_phone("+263 77 123 4567") == "+263771234567"


@pytest.mark.parametrize("bad", ["abc", "123", "+263 12", "", "+999999999999999999"])
def test_invalid_phone_numbers_are_rejected(bad):
    with pytest.raises(ApiError) as caught:
        svc.normalise_phone(bad, "+263")
    assert caught.value.code == "INVALID_PHONE"


def test_phone_is_encrypted_and_digest_is_keyed_and_stable():
    settings = make_settings()
    cipher = svc.encrypt_phone(settings, "+263771234567")
    assert "263771234567" not in cipher
    assert svc.decrypt_phone(settings, cipher) == "+263771234567"
    digest = svc.keyed_digest(settings, "phone:+263771234567")
    assert digest == svc.keyed_digest(settings, "phone:+263771234567")
    assert digest != svc.keyed_digest(make_settings(subscriber_digest_key="another-key"), "phone:+263771234567")


def test_preferences_require_a_scope_and_known_values():
    settings = make_settings()
    with pytest.raises(ApiError) as caught:
        svc.validate_preferences(settings, False, [], [])
    assert caught.value.code == "PREFERENCES_REQUIRED"
    with pytest.raises(ApiError):
        svc.validate_preferences(settings, False, ["Narnia"], [])
    with pytest.raises(ApiError):
        svc.validate_preferences(settings, False, [], ["A9 Nowhere"])
    prefs = svc.validate_preferences(settings, False, ["harare", "Harare"], ["a3 harare-mutare"])
    assert prefs.provinces == ["Harare"] and prefs.corridors == ["A3 Harare-Mutare"]


def test_rate_limit_blocks_after_the_limit_and_recovers():
    reset_rate_limits()
    for i in range(3):
        check_rate_limit("t", "1.2.3.4", 3, now=100.0 + i)
    with pytest.raises(ApiError) as caught:
        check_rate_limit("t", "1.2.3.4", 3, now=103.0)
    assert caught.value.status_code == 429 and "Retry-After" in (caught.value.headers or {})
    check_rate_limit("t", "5.6.7.8", 3, now=103.0)  # another client is unaffected
    check_rate_limit("t", "1.2.3.4", 3, now=161.0)  # window passed
    reset_rate_limits()


def test_province_helpers():
    assert normalise_province("  harare ") == "Harare"
    assert normalise_province("Atlantis") is None
    assert detect_province("Crash near Marondera, Mashonaland East") == "Mashonaland East"
    assert detect_province("Between Harare and Bulawayo") is None  # two provinces: not guessed
    assert detect_province(None) is None


def test_summary_text_is_short_and_word_safe():
    assert make_summary_text("Short text.") == "Short text."
    long = make_summary_text("word " * 200)
    assert len(long) <= 245 and long.endswith("...")


def test_public_schemas_have_no_internal_fields():
    forbidden = {
        "credibility_score", "geographic_risk_score", "review_priority", "notes", "reviewer_id",
        "extraction_output", "location_candidates", "evidence", "phone", "created_by",
    }
    for model in (PublicAlertSummary, PublicAlertDetail):
        assert forbidden.isdisjoint(model.model_fields), model.__name__


def test_mock_routing_never_invents_places_and_flags_itself():
    provider = MockRoutingProvider(PLACES)
    with pytest.raises(RoutingError):
        provider.geocode("Atlantis")
    route = provider.route([PLACES["harare"], PLACES["mutare"]], "drive")
    assert route.provider == "mock" and route.warnings
    assert provider.geocode("Harare").latitude == PLACES["harare"][0]


def test_mock_routing_failure_mode_raises_unavailable():
    with pytest.raises(RoutingUnavailable):
        MockRoutingProvider(PLACES, fail="unavailable").route([PLACES["harare"], PLACES["mutare"]], "drive")


def test_geoapify_needs_a_key():
    with pytest.raises(RoutingUnavailable):
        GeoapifyProvider(make_settings(routing_provider="geoapify"))


def test_mock_notification_provider_is_labelled_and_idempotent():
    provider = MockNotificationProvider()
    assert provider.is_mock and provider.name == "mock"
    first = provider.send_alert("+263771234567", "hello", idempotency_key="k1")
    again = provider.send_alert("+263771234567", "hello", idempotency_key="k1")
    assert first.status == "sent" and again.provider_reference == "mock-duplicate-suppressed"
    assert len(provider.messages) == 1
    provider.fail_next = 1
    assert provider.send_alert("+263771234567", "x", idempotency_key="k2").status == "failed"
