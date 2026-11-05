"""Outbound WhatsApp client: the official Meta Cloud API, or a recording mock.

``build_client`` returns the mock unless ``WHATSAPP_SEND_MODE=live`` *and* the credentials are
present, so nothing reaches a real phone by accident. The live client:

* posts to ``https://graph.facebook.com/<version>/<phone-number-id>/messages`` with a Bearer token;
* has a hard timeout, and retries only when retrying cannot double-send: HTTP 429 / 5xx answers
  and connection failures. A read timeout (the message may have been accepted) is reported as
  ``unknown`` and not retried;
* never logs the token, the message text or the recipient number.

Send-once semantics (idempotency) are provided by ``app.services.whatsapp.outbound``, which keeps
the ``whatsapp_outbound`` log; a client is only asked to send.
"""

from __future__ import annotations

import itertools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.integrations.whatsapp.messages import OutboundMessage, image_payload, template_payload, to_payload
from app.services.notifications.base import SendResult

log = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class WhatsAppClient(Protocol):
    name: str
    is_mock: bool

    def send(self, to_wa_id: str, message: OutboundMessage) -> SendResult: ...

    def send_template(self, to_wa_id: str, name: str, language: str, body_params: list[str]) -> SendResult: ...


# --------------------------------------------------------------------------- mock


@dataclass
class MockSent:
    to_wa_id: str
    kind: str  # text | buttons | list | template
    body: str
    choices: tuple[str, ...] = ()


@dataclass
class MockWhatsAppClient:
    """Records everything it is asked to send; sends nothing."""

    name: str = "mock"
    is_mock: bool = True
    fail_next: int = 0
    sent: list[MockSent] = field(default_factory=list)
    _counter: itertools.count = field(default_factory=itertools.count, repr=False)

    def _record(self, item: MockSent) -> SendResult:
        if self.fail_next > 0:
            self.fail_next -= 1
            return SendResult(status="failed", error="mock client failure")
        self.sent.append(item)
        return SendResult(status="sent", provider_reference=f"mock.wamid.{next(self._counter)}")

    def send(self, to_wa_id: str, message: OutboundMessage) -> SendResult:
        return self._record(MockSent(to_wa_id, message.kind, message.body, tuple(c.id for c in message.choices)))

    def send_template(self, to_wa_id: str, name: str, language: str, body_params: list[str]) -> SendResult:
        return self._record(MockSent(to_wa_id, "template", f"{name}: " + " | ".join(body_params)))

    def texts_to(self, to_wa_id: str) -> list[str]:
        return [m.body for m in self.sent if m.to_wa_id == to_wa_id]


# --------------------------------------------------------------------------- live


class MetaCloudClient:
    name = "meta_cloud"
    is_mock = False

    def __init__(
        self,
        settings: Settings,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if settings.whatsapp_access_token is None or not settings.whatsapp_phone_number_id:
            raise RuntimeError("WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID are required for live sending.")
        self._url = (
            f"{GRAPH_BASE}/{settings.whatsapp_graph_api_version}/{settings.whatsapp_phone_number_id}/messages"
        )
        self._media_url = (
            f"{GRAPH_BASE}/{settings.whatsapp_graph_api_version}/{settings.whatsapp_phone_number_id}/media"
        )
        self._token = settings.whatsapp_access_token.get_secret_value()
        self._timeout = settings.whatsapp_api_timeout_seconds
        self._retries = settings.whatsapp_api_max_retries
        self._http = http or httpx.Client(timeout=self._timeout)
        self._sleep = sleep

    def send(self, to_wa_id: str, message: OutboundMessage) -> SendResult:
        if message.kind == "image" and message.image:
            media_id = self._upload_image(message.image)
            if media_id is not None:
                return self._post(image_payload(to_wa_id, media_id, message.body))
            log.warning("WhatsApp image upload failed; sending the caption as text")
        return self._post(to_payload(to_wa_id, message))  # an image kind with no usable image goes out as its text

    def _upload_image(self, data: bytes) -> str | None:
        """Upload to WhatsApp media; None on any failure so the caller can fall back to text."""
        try:
            response = self._http.post(
                self._media_url,
                headers={"Authorization": f"Bearer {self._token}"},
                data={"messaging_product": "whatsapp", "type": "image/jpeg"},
                files={"file": ("map.jpg", data, "image/jpeg")},
                timeout=self._timeout,
            )
            if response.status_code >= 400:
                log.warning("WhatsApp media upload rejected: http=%s code=%s", response.status_code, _error_code(response))
                return None
            return str(response.json()["id"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return None

    def send_template(self, to_wa_id: str, name: str, language: str, body_params: list[str]) -> SendResult:
        return self._post(template_payload(to_wa_id, name, language, body_params))

    def _post(self, payload: dict[str, Any]) -> SendResult:
        headers = {"Authorization": f"Bearer {self._token}"}
        last_error = "request failed"
        for attempt in range(self._retries + 1):
            if attempt:
                self._sleep(min(2 ** (attempt - 1), 8))
            try:
                response = self._http.post(self._url, json=payload, headers=headers, timeout=self._timeout)
            except httpx.ConnectError:
                last_error = "could not connect to WhatsApp"
                continue  # nothing reached the server: safe to retry
            except httpx.TimeoutException:
                log.warning("WhatsApp send timed out; outcome unknown")
                return SendResult(status="unknown", error="WhatsApp did not answer in time")
            except httpx.HTTPError:
                last_error = "WhatsApp request error"
                continue
            if response.status_code in RETRY_STATUSES:
                last_error = f"WhatsApp answered {response.status_code}"
                continue
            if response.status_code >= 400:
                # Client errors (bad token, window closed, template not approved) will not fix themselves.
                code = _error_code(response)
                log.warning("WhatsApp rejected a message: http=%s code=%s", response.status_code, code)
                return SendResult(status="failed", error=f"WhatsApp rejected the message (http {response.status_code}, code {code})")
            try:
                message_id = response.json()["messages"][0]["id"]
            except (ValueError, KeyError, IndexError, TypeError):
                return SendResult(status="unknown", error="WhatsApp answered without a message id")
            return SendResult(status="sent", provider_reference=message_id)
        log.warning("WhatsApp send failed after retries: %s", last_error)
        return SendResult(status="failed", error=last_error)


def _error_code(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", {}).get("code", "?"))
    except (ValueError, AttributeError):
        return "?"


# --------------------------------------------------------------------------- factory

_MOCK = MockWhatsAppClient()


def build_client(settings: Settings, http: httpx.Client | None = None) -> WhatsAppClient:
    """Live client only when explicitly switched on and fully configured; the mock otherwise."""
    if settings.whatsapp_send_mode == "live":
        return MetaCloudClient(settings, http=http)
    return _MOCK


def reset_mock_client() -> None:
    _MOCK.sent.clear()
    _MOCK.fail_next = 0
