"""Notification provider interface (SMS / WhatsApp).

Real providers must honour recipient opt-in, approved templates and messaging windows
(WhatsApp), and must report what they actually know: ``sent`` means accepted by the provider,
``delivered`` only when a delivery receipt says so, ``unknown`` when we cannot tell.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

SendStatus = Literal["sent", "failed", "unknown"]


@dataclass(frozen=True)
class SendResult:
    status: SendStatus
    provider_reference: str | None = None
    error: str | None = None  # client-safe, never contains the recipient or message text


class NotificationProvider(Protocol):
    name: str
    channel: str  # "sms" | "whatsapp"
    is_mock: bool

    def send_verification(self, to_e164: str, code: str, *, idempotency_key: str) -> SendResult: ...

    def send_optin_confirmation(self, to_e164: str, *, idempotency_key: str) -> SendResult: ...

    def send_alert(self, to_e164: str, text: str, *, idempotency_key: str, image: bytes | None = None) -> SendResult: ...


class SMSProvider(NotificationProvider, Protocol):
    channel: str


class WhatsAppProvider(NotificationProvider, Protocol):
    """Real implementations must send only approved templates and respect the 24h window."""

    channel: str
