"""Phone alert subscription endpoints. No accounts, no cookies, no CSRF surface.

Management uses a short-lived bearer token obtained only by verifying a one-time code sent to
the number itself, so nobody can read or change another person's subscription by typing their
number. Registration, resend and recovery always answer identically.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import AppSettings, DbSession
from app.api.errors import ERROR_RESPONSES
from app.api.rate_limit import WriteLimit, client_ip
from app.models.subscription import SubscriberChannel
from app.schemas.common import ApiModel, UtcDatetime
from app.services import subscriptions as svc
from app.services.zimbabwe import PROVINCES

router = APIRouter(prefix="/public/subscriptions", tags=["public-subscriptions"], responses=ERROR_RESPONSES)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PhoneInput(_Strict):
    phone: str = Field(min_length=5, max_length=32)
    country_code: str = Field(default="+263", max_length=6)


class SubscribeRequest(PhoneInput):
    channel: SubscriberChannel
    all_zimbabwe: bool = False
    provinces: list[str] = Field(default_factory=list, max_length=10)
    corridors: list[str] = Field(default_factory=list, max_length=10)
    consent_accepted: bool
    consent_version: str = Field(max_length=32)


class VerifyRequest(PhoneInput):
    code: str = Field(pattern=r"^\d{6}$")


class PreferencesPatch(_Strict):
    all_zimbabwe: bool
    provinces: list[str] = Field(default_factory=list, max_length=10)
    corridors: list[str] = Field(default_factory=list, max_length=10)


class AckOut(ApiModel):
    status: str
    message: str
    mock_code: str | None = Field(default=None, description="Only in local mock mode with MOCK_EXPOSE_CODES.")


class VerifyOut(ApiModel):
    management_token: str
    expires_at: UtcDatetime
    activated: bool


class PreferencesOut(ApiModel):
    channel: str
    all_zimbabwe: bool
    provinces: list[str]
    corridors: list[str]


class OptionsOut(ApiModel):
    provinces: list[str]
    corridors: list[str]
    channels: list[str]
    consent_version: str
    consent_text: str
    default_country_code: str
    messaging_mode: str


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    return None


def _ack(settings, code: str | None) -> AckOut:
    exposed = code if (settings.notification_provider == "mock" and settings.mock_expose_codes) else None
    message = f"Enter the code {settings.subscriber_fixed_code} to confirm." if settings.subscriber_fixed_code else svc.UNIFORM_MESSAGE
    return AckOut(status="verification_requested", message=message, mock_code=exposed)


@router.get("/options", response_model=OptionsOut)
def get_subscription_options(settings: AppSettings) -> OptionsOut:
    return OptionsOut(
        provinces=list(PROVINCES),
        corridors=svc.configured_corridors(settings),
        channels=[c.value for c in SubscriberChannel],
        consent_version=svc.CONSENT_VERSION,
        consent_text=svc.CONSENT_TEXT,
        default_country_code="+263",
        messaging_mode=settings.notification_provider,
    )


@router.post("", response_model=AckOut, status_code=202, dependencies=[WriteLimit])
def create_subscription(body: SubscribeRequest, request: Request, db: DbSession, settings: AppSettings) -> AckOut:
    e164 = svc.normalise_phone(body.phone, body.country_code)
    prefs = svc.validate_preferences(settings, body.all_zimbabwe, body.provinces, body.corridors)
    code = svc.register(
        db,
        settings,
        e164=e164,
        channel=body.channel,
        prefs=prefs,
        consent_accepted=body.consent_accepted,
        consent_version=body.consent_version,
        ip_digest=svc.keyed_digest(settings, f"ip:{client_ip(request, settings)}"),
        user_agent=request.headers.get("user-agent"),
    )
    return _ack(settings, code)


@router.post("/resend-verification", response_model=AckOut, status_code=202, dependencies=[WriteLimit])
def resend_verification(body: PhoneInput, db: DbSession, settings: AppSettings) -> AckOut:
    """Also the recovery path for managing an existing subscription. Always the same answer."""
    e164 = svc.normalise_phone(body.phone, body.country_code)
    code = svc.resend(db, settings, e164=e164)
    return _ack(settings, code)


@router.post("/verify", response_model=VerifyOut, dependencies=[WriteLimit])
def verify_subscription(body: VerifyRequest, db: DbSession, settings: AppSettings) -> VerifyOut:
    e164 = svc.normalise_phone(body.phone, body.country_code)
    verified = svc.verify(db, settings, e164=e164, code=body.code)
    return VerifyOut(
        management_token=verified.token, expires_at=verified.expires_at, activated=verified.activated
    )


@router.get("/preferences", response_model=PreferencesOut, dependencies=[WriteLimit])
def get_subscription_preferences(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> PreferencesOut:
    subscriber = svc.subscriber_for_token(db, _bearer(authorization))
    prefs = svc.get_preferences(db, subscriber)
    return PreferencesOut(
        channel=subscriber.channel,
        all_zimbabwe=prefs.all_zimbabwe,
        provinces=list(prefs.provinces),
        corridors=list(prefs.corridors),
    )


@router.patch("/preferences", response_model=PreferencesOut, dependencies=[WriteLimit])
def update_subscription_preferences(
    body: PreferencesPatch,
    db: DbSession,
    settings: AppSettings,
    authorization: Annotated[str | None, Header()] = None,
) -> PreferencesOut:
    subscriber = svc.subscriber_for_token(db, _bearer(authorization))
    prefs = svc.validate_preferences(settings, body.all_zimbabwe, body.provinces, body.corridors)
    row = svc.update_preferences(db, subscriber, prefs)
    return PreferencesOut(
        channel=subscriber.channel,
        all_zimbabwe=row.all_zimbabwe,
        provinces=list(row.provinces),
        corridors=list(row.corridors),
    )


@router.post("/unsubscribe", response_model=AckOut, dependencies=[WriteLimit])
def unsubscribe_subscription(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> AckOut:
    subscriber = svc.subscriber_for_token(db, _bearer(authorization))
    svc.unsubscribe(db, subscriber)
    return AckOut(status="unsubscribed", message="You will no longer receive SafeRouteZW alerts.")
