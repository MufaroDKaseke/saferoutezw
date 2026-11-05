"""MOCK notification provider. It sends nothing to any phone.

Messages are kept in memory so tests and the local demo can inspect them. Every result is
labelled ``mock`` and a "sent" status only means "recorded locally", never real delivery.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from app.services.notifications.base import SendResult


@dataclass
class MockMessage:
    kind: str  # verification | optin | alert
    to_e164: str
    body: str
    idempotency_key: str
    code: str | None = None
    has_image: bool = False


@dataclass
class MockNotificationProvider:
    channel: str = "sms"
    name: str = "mock"
    is_mock: bool = True
    fail_next: int = 0  # simulate this many consecutive provider failures
    unknown_next: int = 0  # simulate this many "cannot tell" outcomes
    messages: list[MockMessage] = field(default_factory=list)
    _counter: itertools.count = field(default_factory=itertools.count, repr=False)

    def _record(self, message: MockMessage) -> SendResult:
        if self.fail_next > 0:
            self.fail_next -= 1
            return SendResult(status="failed", error="mock provider failure")
        if self.unknown_next > 0:
            self.unknown_next -= 1
            return SendResult(status="unknown", error="mock provider gave no answer")
        # Idempotency: the same key is never recorded twice.
        if any(m.idempotency_key == message.idempotency_key for m in self.messages):
            return SendResult(status="sent", provider_reference="mock-duplicate-suppressed")
        self.messages.append(message)
        return SendResult(status="sent", provider_reference=f"mock-{next(self._counter)}")

    def send_verification(self, to_e164: str, code: str, *, idempotency_key: str) -> SendResult:
        body = f"[MOCK] SafeRouteZW verification code: {code}"
        return self._record(MockMessage("verification", to_e164, body, idempotency_key, code=code))

    def send_optin_confirmation(self, to_e164: str, *, idempotency_key: str) -> SendResult:
        body = "[MOCK] You are subscribed to SafeRouteZW road alerts. Reply STOP to unsubscribe."
        return self._record(MockMessage("optin", to_e164, body, idempotency_key))

    def send_alert(self, to_e164: str, text: str, *, idempotency_key: str, image: bytes | None = None) -> SendResult:
        return self._record(MockMessage("alert", to_e164, f"[MOCK] {text}", idempotency_key, has_image=image is not None))

    def last_code_for(self, to_e164: str) -> str | None:
        for message in reversed(self.messages):
            if message.kind == "verification" and message.to_e164 == to_e164:
                return message.code
        return None
