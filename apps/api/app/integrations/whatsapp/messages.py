"""WhatsApp Cloud API message shapes: parse inbound webhooks, build outbound payloads.

Only what the bot needs is read from a webhook, and only that is kept: the text, an interactive
reply id, or a location pin. Media is recognised but never downloaded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# WhatsApp's documented limits for interactive messages.
MAX_TEXT = 4096
MAX_BODY = 1024
MAX_BUTTONS = 3
MAX_BUTTON_TITLE = 20
MAX_LIST_ROWS = 10
MAX_ROW_TITLE = 24
MAX_ROW_DESCRIPTION = 72
MAX_LIST_BUTTON = 20

# Inbound message kinds the bot understands. Anything else is "unsupported".
TEXT, REPLY, LOCATION, MEDIA, UNSUPPORTED = "text", "reply", "location", "media", "unsupported"
MEDIA_TYPES = frozenset({"image", "video", "audio", "document", "sticker"})


@dataclass(frozen=True)
class InboundEvent:
    wamid: str
    wa_id: str  # sender's WhatsApp id (their phone number, digits only)
    kind: str
    text: str | None = None
    reply_id: str | None = None  # id of the tapped button / list row
    latitude: float | None = None
    longitude: float | None = None
    sent_at: datetime | None = None

    def payload(self) -> dict[str, Any]:
        """The minimum stored for later processing (no phone number, no profile name)."""
        data: dict[str, Any] = {}
        if self.text is not None:
            data["text"] = self.text
        if self.reply_id is not None:
            data["reply_id"] = self.reply_id
        if self.latitude is not None and self.longitude is not None:
            data["latitude"], data["longitude"] = self.latitude, self.longitude
        return data


@dataclass(frozen=True)
class StatusEvent:
    provider_message_id: str
    status: str  # sent | delivered | read | failed
    error_code: str | None = None


@dataclass(frozen=True)
class ParsedWebhook:
    messages: list[InboundEvent] = field(default_factory=list)
    statuses: list[StatusEvent] = field(default_factory=list)


def _timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if -180 <= number <= 180 else None


def _parse_message(raw: dict[str, Any]) -> InboundEvent | None:
    wamid, sender = raw.get("id"), raw.get("from")
    if not isinstance(wamid, str) or not wamid or not isinstance(sender, str) or not sender.isdigit():
        return None
    base: dict[str, Any] = {"wamid": wamid, "wa_id": sender, "sent_at": _timestamp(raw.get("timestamp"))}
    kind = raw.get("type")
    if kind == "text":
        body = (raw.get("text") or {}).get("body")
        if isinstance(body, str):
            return InboundEvent(kind=TEXT, text=body[:MAX_TEXT], **base)
    elif kind == "interactive":
        interactive = raw.get("interactive") or {}
        reply = interactive.get(interactive.get("type") or "") or {}
        if isinstance(reply, dict) and isinstance(reply.get("id"), str):
            return InboundEvent(kind=REPLY, reply_id=reply["id"][:200], text=str(reply.get("title") or "")[:200], **base)
    elif kind == "button":  # quick-reply button on a template message
        button = raw.get("button") or {}
        payload = button.get("payload") or button.get("text")
        if isinstance(payload, str):
            return InboundEvent(kind=TEXT, text=payload[:MAX_TEXT], **base)
    elif kind == "location":
        loc = raw.get("location") or {}
        lat, lon = _float(loc.get("latitude")), _float(loc.get("longitude"))
        if lat is not None and lon is not None and -90 <= lat <= 90:
            return InboundEvent(kind=LOCATION, latitude=lat, longitude=lon, **base)
    elif kind in MEDIA_TYPES:
        return InboundEvent(kind=MEDIA, **base)
    return InboundEvent(kind=UNSUPPORTED, **base)


def parse_webhook(body: dict[str, Any]) -> ParsedWebhook:
    """Extract messages and delivery statuses from a Cloud API webhook body. Malformed parts are skipped."""
    parsed = ParsedWebhook()
    if body.get("object") != "whatsapp_business_account":
        return parsed
    for entry in body.get("entry") or []:
        for change in (entry or {}).get("changes") or []:
            value = (change or {}).get("value") or {}
            for raw in value.get("messages") or []:
                if isinstance(raw, dict) and (event := _parse_message(raw)) is not None:
                    parsed.messages.append(event)
            for raw in value.get("statuses") or []:
                if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
                    continue
                status = raw.get("status")
                if status not in ("sent", "delivered", "read", "failed"):
                    continue
                errors = raw.get("errors") or []
                code = str((errors[0] or {}).get("code")) if errors and isinstance(errors[0], dict) else None
                parsed.statuses.append(StatusEvent(raw["id"], status, code))
    return parsed


# --------------------------------------------------------------------------- outbound


@dataclass(frozen=True)
class Choice:
    id: str
    title: str
    description: str | None = None


@dataclass(frozen=True)
class OutboundMessage:
    """A reply: plain text, up to 3 buttons, or a list of up to 10 rows."""

    kind: str  # text | buttons | list
    body: str
    choices: tuple[Choice, ...] = ()
    list_button: str = "Choose"


def text_message(body: str) -> OutboundMessage:
    return OutboundMessage("text", body[:MAX_TEXT])


def buttons_message(body: str, choices: list[Choice]) -> OutboundMessage:
    return OutboundMessage("buttons", body[:MAX_BODY], tuple(choices[:MAX_BUTTONS]))


def list_message(body: str, choices: list[Choice], button: str = "Choose") -> OutboundMessage:
    return OutboundMessage("list", body[:MAX_BODY], tuple(choices[:MAX_LIST_ROWS]), button[:MAX_LIST_BUTTON])


def to_payload(to_wa_id: str, message: OutboundMessage) -> dict[str, Any]:
    """The JSON body for ``POST /{phone-number-id}/messages``."""
    base: dict[str, Any] = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": to_wa_id}
    if message.kind == "buttons":
        return {
            **base,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": message.body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": c.id, "title": c.title[:MAX_BUTTON_TITLE]}}
                        for c in message.choices
                    ]
                },
            },
        }
    if message.kind == "list":
        return {
            **base,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": message.body},
                "action": {
                    "button": message.list_button,
                    "sections": [
                        {
                            "title": "Options",
                            "rows": [
                                {
                                    "id": c.id,
                                    "title": c.title[:MAX_ROW_TITLE],
                                    **({"description": c.description[:MAX_ROW_DESCRIPTION]} if c.description else {}),
                                }
                                for c in message.choices
                            ],
                        }
                    ],
                },
            },
        }
    return {**base, "type": "text", "text": {"preview_url": False, "body": message.body}}


def template_payload(to_wa_id: str, name: str, language: str, body_params: list[str]) -> dict[str, Any]:
    return {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": name,
            "language": {"code": language},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": p[:1000]} for p in body_params]}
            ]
            if body_params
            else [],
        },
    }
