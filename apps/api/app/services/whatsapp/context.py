"""Shared plumbing for the bot's three flows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.integrations.whatsapp.messages import LOCATION, MEDIA, REPLY, TEXT, OutboundMessage
from app.models import WhatsAppConversation, WhatsAppInbound
from app.services.routing.base import RoutingProvider
from app.services.whatsapp.outbound import Replier

MENU, CHOOSE, START = "menu", "choose", "start"


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float


class PlaceResolver:
    """Turns a typed place name into candidate places. Raises ``PlaceLookupUnavailable`` if it cannot."""

    def candidates(self, query: str) -> list[Place]:  # pragma: no cover - interface
        raise NotImplementedError


class PlaceLookupUnavailable(Exception):
    """The geocoding service is missing or failing (not 'place not found')."""


@dataclass
class Deps:
    """Everything the flows reach outside the database for, injectable in tests and the simulator."""

    resolver: PlaceResolver
    routing_provider: Callable[[Settings], RoutingProvider]


@dataclass(frozen=True)
class Event:
    wamid: str
    kind: str
    text: str | None = None
    reply_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    sent_at: datetime | None = None

    @classmethod
    def from_row(cls, row: WhatsAppInbound) -> Event:
        p = row.payload or {}
        return cls(
            wamid=row.wamid,
            kind=row.kind,
            text=p.get("text"),
            reply_id=p.get("reply_id"),
            latitude=p.get("latitude"),
            longitude=p.get("longitude"),
            sent_at=row.sent_at,
        )

    @property
    def is_text(self) -> bool:
        return self.kind == TEXT

    @property
    def is_reply(self) -> bool:
        return self.kind == REPLY

    @property
    def is_location(self) -> bool:
        return self.kind == LOCATION

    @property
    def is_media(self) -> bool:
        return self.kind == MEDIA

    @property
    def choice(self) -> str:
        """What the user picked or typed, upper-cased and whitespace-collapsed ('' for pins and media)."""
        raw = self.reply_id if self.is_reply else (self.text if self.is_text else "")
        return " ".join((raw or "").upper().split())

    @property
    def free_text(self) -> str:
        """Typed text, or the title of a tapped option; whitespace-collapsed, original case."""
        return " ".join((self.text or "").split()) if (self.is_text or self.is_reply) else ""


@dataclass
class Ctx:
    session: Session
    settings: Settings
    conv: WhatsAppConversation
    wa_id: str
    event: Event
    replier: Replier
    deps: Deps
    now: datetime
    _sent: int = field(default=0, repr=False)

    @property
    def e164(self) -> str:
        return "+" + self.wa_id

    @property
    def data(self) -> dict[str, Any]:
        return dict(self.conv.data or {})

    def say(self, message: OutboundMessage) -> None:
        self.replier.send(self.wa_id, message, key=f"reply:{self.event.wamid}:{self._sent}")
        self._sent += 1

    def goto(self, flow: str, step: str, **data: Any) -> None:
        self.conv.flow, self.conv.step = flow, step
        if data:
            self.conv.data = {**self.data, **data}

    def set(self, **data: Any) -> None:
        self.conv.data = {**self.data, **data}

    def reset(self) -> None:
        """Back to the menu with the draft erased."""
        self.conv.flow, self.conv.step, self.conv.data = MENU, CHOOSE, {}
