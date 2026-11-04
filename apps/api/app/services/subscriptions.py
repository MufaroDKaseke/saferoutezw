"""Phone alert subscriptions: normalisation, protection at rest, verification, consent, management.

Rules enforced here:
* a number never becomes active until a one-time code was verified AND consent was recorded;
* phone numbers are encrypted at rest (Fernet); a keyed HMAC digest de-duplicates them;
* one-time codes and management tokens are stored only as keyed/plain hashes;
* registering, resending and recovering give one uniform answer, so nothing reveals whether a
  number is already subscribed;
* verification has an expiry, an attempt limit, a resend cooldown and an hourly cap.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import phonenumbers
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.config import Settings
from app.models import (
    AlertSubscriber,
    SubscriptionChallenge,
    SubscriptionConsent,
    SubscriptionPreference,
    SubscriptionToken,
)
from app.models.subscription import ChallengePurpose, SubscriberChannel, SubscriberStatus
from app.services.audit import record_audit
from app.services.notifications import get_notification_provider
from app.services.zimbabwe import normalise_province

log = logging.getLogger(__name__)

CONSENT_VERSION = "2026-11-v1"
CONSENT_TEXT = (
    "I agree to receive SafeRouteZW road safety alerts on this number by {channel}. "
    "Alerts are based on reviewed reports and may be incomplete. Message and data rates may apply. "
    "I can unsubscribe at any time."
)
UNIFORM_MESSAGE = "If the number can receive alerts, a verification code has been sent to it."
INVALID_CODE = ApiError(400, "INVALID_CODE", "That code is not valid or has expired.")
INVALID_TOKEN = ApiError(401, "INVALID_TOKEN", "Your session has expired. Verify your number again.")

# Development fallback only (mock provider). Production must set both keys.
_DEV_SECRET = b"saferoutezw-dev-only-insecure-key"


def _dev_fallback_ok(settings: Settings) -> bool:
    return settings.notification_provider == "mock"


def _fernet(settings: Settings) -> Fernet:
    if settings.subscriber_encryption_key is not None:
        return Fernet(settings.subscriber_encryption_key.get_secret_value().encode())
    if not _dev_fallback_ok(settings):
        raise RuntimeError("SUBSCRIBER_ENCRYPTION_KEY is required.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_DEV_SECRET).digest()))


def _digest_key(settings: Settings) -> bytes:
    if settings.subscriber_digest_key is not None:
        return settings.subscriber_digest_key.get_secret_value().encode()
    if not _dev_fallback_ok(settings):
        raise RuntimeError("SUBSCRIBER_DIGEST_KEY is required.")
    return _DEV_SECRET


def keyed_digest(settings: Settings, value: str) -> str:
    return hmac.new(_digest_key(settings), value.encode(), hashlib.sha256).hexdigest()


def encrypt_phone(settings: Settings, e164: str) -> str:
    return _fernet(settings).encrypt(e164.encode()).decode()


def decrypt_phone(settings: Settings, ciphertext: str) -> str:
    try:
        return _fernet(settings).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise RuntimeError("Stored phone number cannot be decrypted with the configured key.") from None


def normalise_phone(phone: str, country_code: str = "+263") -> str:
    """Return E.164 or raise a 422. Accepts '+263 77 123 4567', '077 123 4567' with a country code."""
    raw = phone.strip()
    if not raw.startswith("+"):
        cc = country_code.strip()
        if not cc.startswith("+") or not cc[1:].isdigit():
            raise ApiError(422, "INVALID_PHONE", "Enter a valid phone number.")
        raw = cc + raw.lstrip("0").replace(" ", "")
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        raise ApiError(422, "INVALID_PHONE", "Enter a valid phone number.") from None
    if not phonenumbers.is_valid_number(parsed):
        raise ApiError(422, "INVALID_PHONE", "Enter a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def configured_corridors(settings: Settings) -> list[str]:
    return [c.strip() for c in settings.subscription_corridors.split(",") if c.strip()]


@dataclass(frozen=True)
class PreferenceInput:
    all_zimbabwe: bool
    provinces: list[str]
    corridors: list[str]


def validate_preferences(settings: Settings, all_zimbabwe: bool, provinces: list[str], corridors: list[str]) -> PreferenceInput:
    canon: list[str] = []
    for p in provinces:
        c = normalise_province(p)
        if c is None:
            raise ApiError(422, "INVALID_PROVINCE", "That is not a Zimbabwe province.")
        if c not in canon:
            canon.append(c)
    allowed = {c.lower(): c for c in configured_corridors(settings)}
    chosen: list[str] = []
    for c in corridors:
        match = allowed.get(c.strip().lower())
        if match is None:
            raise ApiError(422, "INVALID_CORRIDOR", "That road corridor is not available.")
        if match not in chosen:
            chosen.append(match)
    if not (all_zimbabwe or canon or chosen):
        raise ApiError(422, "PREFERENCES_REQUIRED", "Choose a province, a road corridor, or all of Zimbabwe.")
    return PreferenceInput(all_zimbabwe=all_zimbabwe, provinces=canon, corridors=chosen)


# --- one-time codes --------------------------------------------------------------------------


def _code_hash(settings: Settings, subscriber_id: uuid.UUID, purpose: str, code: str) -> str:
    return keyed_digest(settings, f"otp:{subscriber_id}:{purpose}:{code}")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _issue_challenge(
    session: Session, settings: Settings, subscriber: AlertSubscriber, purpose: str
) -> str | None:
    """Create and send a code unless the cooldown or hourly cap applies. Returns the code if sent."""
    now = _now()
    last = session.scalar(
        select(func.max(SubscriptionChallenge.created_at)).where(
            SubscriptionChallenge.subscriber_id == subscriber.id
        )
    )
    if last is not None and (now - last).total_seconds() < settings.otp_resend_cooldown_seconds:
        return None
    recent = session.scalar(
        select(func.count()).where(
            SubscriptionChallenge.subscriber_id == subscriber.id,
            SubscriptionChallenge.created_at >= now - timedelta(hours=1),
        )
    )
    if (recent or 0) >= settings.otp_max_per_hour:
        return None
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge = SubscriptionChallenge(
        subscriber_id=subscriber.id,
        purpose=purpose,
        code_hash=_code_hash(settings, subscriber.id, purpose, code),
        expires_at=now + timedelta(seconds=settings.otp_ttl_seconds),
    )
    session.add(challenge)
    session.flush()
    provider = get_notification_provider(settings, subscriber.channel)
    result = provider.send_verification(
        decrypt_phone(settings, subscriber.phone_ciphertext), code, idempotency_key=f"otp:{challenge.id}"
    )
    if result.status != "sent":
        log.warning("verification message was not sent (status=%s)", result.status)
        return None  # the challenge stays unusable in practice; the user can resend after the cooldown
    return code


# --- public operations -----------------------------------------------------------------------


def _set_preferences(session: Session, subscriber: AlertSubscriber, prefs: PreferenceInput) -> None:
    row = session.scalar(
        select(SubscriptionPreference).where(SubscriptionPreference.subscriber_id == subscriber.id)
    )
    if row is None:
        row = SubscriptionPreference(subscriber_id=subscriber.id)
        session.add(row)
    row.all_zimbabwe = prefs.all_zimbabwe
    row.provinces = prefs.provinces
    row.corridors = prefs.corridors
    row.updated_at = _now()


def register(
    session: Session,
    settings: Settings,
    *,
    e164: str,
    channel: SubscriberChannel,
    prefs: PreferenceInput,
    consent_accepted: bool,
    consent_version: str,
    ip_digest: str | None,
    user_agent: str | None,
) -> str | None:
    """Start (or restart) a subscription. Always the same outward answer. Returns the sent code."""
    if not consent_accepted or consent_version != CONSENT_VERSION:
        raise ApiError(422, "CONSENT_REQUIRED", "You must agree to receive alerts to subscribe.")
    digest = keyed_digest(settings, f"phone:{e164}")
    subscriber = session.scalar(select(AlertSubscriber).where(AlertSubscriber.phone_digest == digest))
    if subscriber is None:
        subscriber = AlertSubscriber(
            phone_ciphertext=encrypt_phone(settings, e164),
            phone_digest=digest,
            channel=channel.value,
            status=SubscriberStatus.PENDING.value,
        )
        session.add(subscriber)
        session.flush()
        purpose = ChallengePurpose.ACTIVATE.value
    elif subscriber.status == SubscriberStatus.ACTIVE.value:
        # Already subscribed: do not change anything, only allow the owner to prove ownership.
        purpose = ChallengePurpose.MANAGE.value
    else:  # pending, or previously unsubscribed: a fresh opt-in is required
        subscriber.channel = channel.value
        subscriber.status = SubscriberStatus.PENDING.value
        subscriber.unsubscribed_at = None
        purpose = ChallengePurpose.ACTIVATE.value

    if purpose == ChallengePurpose.ACTIVATE.value:
        _set_preferences(session, subscriber, prefs)
        session.add(
            SubscriptionConsent(
                subscriber_id=subscriber.id,
                consent_text_version=consent_version,
                channel=channel.value,
                ip_digest=ip_digest,
                user_agent=(user_agent or "")[:300] or None,
            )
        )
    code = _issue_challenge(session, settings, subscriber, purpose)
    session.commit()
    return code


def resend(session: Session, settings: Settings, *, e164: str) -> str | None:
    digest = keyed_digest(settings, f"phone:{e164}")
    subscriber = session.scalar(select(AlertSubscriber).where(AlertSubscriber.phone_digest == digest))
    code = None
    if subscriber is not None and subscriber.status != SubscriberStatus.UNSUBSCRIBED.value:
        purpose = (
            ChallengePurpose.MANAGE.value
            if subscriber.status == SubscriberStatus.ACTIVE.value
            else ChallengePurpose.ACTIVATE.value
        )
        code = _issue_challenge(session, settings, subscriber, purpose)
        session.commit()
    return code


@dataclass(frozen=True)
class VerifiedSession:
    token: str
    expires_at: datetime
    activated: bool


def verify(session: Session, settings: Settings, *, e164: str, code: str) -> VerifiedSession:
    digest = keyed_digest(settings, f"phone:{e164}")
    subscriber = session.scalar(select(AlertSubscriber).where(AlertSubscriber.phone_digest == digest))
    if subscriber is None:
        raise INVALID_CODE
    now = _now()
    challenge = session.scalar(
        select(SubscriptionChallenge)
        .where(SubscriptionChallenge.subscriber_id == subscriber.id, SubscriptionChallenge.used_at.is_(None))
        .order_by(SubscriptionChallenge.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    if challenge is None or challenge.expires_at <= now or challenge.attempts >= settings.otp_max_attempts:
        raise INVALID_CODE
    challenge.attempts += 1
    expected = _code_hash(settings, subscriber.id, challenge.purpose, code.strip())
    if not hmac.compare_digest(expected, challenge.code_hash):
        session.commit()  # persist the failed attempt
        raise INVALID_CODE
    challenge.used_at = now

    activated = False
    if challenge.purpose == ChallengePurpose.ACTIVATE.value:
        has_consent = session.scalar(
            select(func.count()).where(
                SubscriptionConsent.subscriber_id == subscriber.id, SubscriptionConsent.withdrawn_at.is_(None)
            )
        )
        if not has_consent:
            session.commit()
            raise INVALID_CODE
        subscriber.status = SubscriberStatus.ACTIVE.value
        subscriber.verified_at = now
        activated = True
        get_notification_provider(settings, subscriber.channel).send_optin_confirmation(
            decrypt_phone(settings, subscriber.phone_ciphertext), idempotency_key=f"optin:{subscriber.id}:{now:%Y%m%d%H%M%S}"
        )
    if subscriber.status != SubscriberStatus.ACTIVE.value:
        session.commit()
        raise INVALID_CODE

    token = secrets.token_urlsafe(32)
    expires = now + timedelta(minutes=settings.management_token_ttl_minutes)
    session.add(SubscriptionToken(subscriber_id=subscriber.id, token_hash=_token_hash(token), expires_at=expires))
    record_audit(
        session,
        actor_id=None,
        action="subscription.activated" if activated else "subscription.verified",
        entity_type="subscriber",
        entity_id=subscriber.id,
        details={"channel": subscriber.channel},
    )
    session.commit()
    return VerifiedSession(token=token, expires_at=expires, activated=activated)


def subscriber_for_token(session: Session, token: str | None) -> AlertSubscriber:
    if not token:
        raise INVALID_TOKEN
    row = session.scalar(
        select(SubscriptionToken).where(
            SubscriptionToken.token_hash == _token_hash(token), SubscriptionToken.expires_at > _now()
        )
    )
    if row is None:
        raise INVALID_TOKEN
    subscriber = session.get(AlertSubscriber, row.subscriber_id)
    if subscriber is None or subscriber.status != SubscriberStatus.ACTIVE.value:
        raise INVALID_TOKEN
    return subscriber


def get_preferences(session: Session, subscriber: AlertSubscriber) -> SubscriptionPreference:
    row = session.scalar(
        select(SubscriptionPreference).where(SubscriptionPreference.subscriber_id == subscriber.id)
    )
    if row is None:
        row = SubscriptionPreference(subscriber_id=subscriber.id, all_zimbabwe=False, provinces=[], corridors=[])
        session.add(row)
        session.flush()
    return row


def update_preferences(session: Session, subscriber: AlertSubscriber, prefs: PreferenceInput) -> SubscriptionPreference:
    _set_preferences(session, subscriber, prefs)
    record_audit(
        session, actor_id=None, action="subscription.preferences_updated", entity_type="subscriber",
        entity_id=subscriber.id, details={},
    )
    session.commit()
    return get_preferences(session, subscriber)


def unsubscribe(session: Session, subscriber: AlertSubscriber) -> None:
    now = _now()
    subscriber.status = SubscriberStatus.UNSUBSCRIBED.value
    subscriber.unsubscribed_at = now
    for consent in session.scalars(
        select(SubscriptionConsent).where(
            SubscriptionConsent.subscriber_id == subscriber.id, SubscriptionConsent.withdrawn_at.is_(None)
        )
    ):
        consent.withdrawn_at = now
    for token in session.scalars(select(SubscriptionToken).where(SubscriptionToken.subscriber_id == subscriber.id)):
        session.delete(token)
    record_audit(
        session, actor_id=None, action="subscription.unsubscribed", entity_type="subscriber",
        entity_id=subscriber.id, details={},
    )
    session.commit()
