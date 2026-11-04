"""Builders for the WhatsApp bot tests. Everything is synthetic and offline.

``Chat`` plays one WhatsApp user: it stores a message exactly as the webhook would, runs the
conversation engine on it, and returns the texts the bot replied with. Sending goes to the
recording ``MockWhatsAppClient``; no network, no real WhatsApp, no OpenAI.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from sqlalchemy import select

from app.integrations.whatsapp.client import MockWhatsAppClient
from app.integrations.whatsapp.messages import InboundEvent, LOCATION, MEDIA, REPLY, TEXT
from app.models import WhatsAppInbound
from app.services.routing.mock import MockRoutingProvider
from app.services.whatsapp import conversation
from app.services.whatsapp.context import Deps, Place
from app.services.whatsapp.inbox import StoreResult, store_message
from app.services.whatsapp.route_check import StaticResolver
from public_helpers import PLACES, make_settings

WA_ID = "263771234567"
_counter = itertools.count(1)


def bot_settings(**overrides):
    values = {
        "whatsapp_enabled": True,
        "whatsapp_app_secret": "test-app-secret",
        "whatsapp_verify_token": "test-verify-token",
        "whatsapp_user_msgs_per_minute": 1000,
        "public_web_base_url": "https://saferoute.example",
    }
    values.update(overrides)
    return make_settings(**values)


def static_resolver(fail: bool = False) -> StaticResolver:
    places = {name: [Place(f"{name.title()}, Zimbabwe", lat, lon)] for name, (lat, lon) in PLACES.items()}
    places["chegutu"] = [  # deliberately ambiguous
        Place("Chegutu, Mashonaland West, Zimbabwe", -18.13, 30.14),
        Place("Chegutu Road, Harare, Zimbabwe", -17.9, 31.0),
    ]
    return StaticResolver(places, fail=fail)


def make_deps(*, fail_geocoder: bool = False, routing: MockRoutingProvider | None = None) -> Deps:
    provider = routing or MockRoutingProvider(PLACES)
    return Deps(resolver=static_resolver(fail_geocoder), routing_provider=lambda settings: provider)


class Chat:
    def __init__(self, session, settings=None, *, wa_id: str = WA_ID, deps: Deps | None = None, client=None):
        self.session = session
        self.settings = settings or bot_settings()
        self.wa_id = wa_id
        self.deps = deps or make_deps()
        self.client = client or MockWhatsAppClient()
        self.now = datetime.now(UTC)

    def _event(self, wamid: str | None, **fields) -> InboundEvent:
        return InboundEvent(wamid=wamid or f"wamid.{next(_counter)}", wa_id=self.wa_id, sent_at=self.now, **fields)

    def deliver(self, event: InboundEvent) -> list[str]:
        """Store the message like the webhook, then process it like the worker. Returns the bot's replies."""
        before = len(self.client.sent)
        store_message(self.session, self.settings, event, StoreResult())
        self.session.commit()
        row = self.session.scalar(select(WhatsAppInbound).where(WhatsAppInbound.wamid == event.wamid))
        if row is None or row.status == "done":
            return []  # dropped (rate limit) or a duplicate that was already handled
        conversation.process(self.session, self.settings, self.client, self.deps, row, now=self.now)
        row.status, row.processed_at, row.payload = "done", self.now, {}
        self.session.commit()
        return [m.body for m in self.client.sent[before:]]

    def say(self, text: str, wamid: str | None = None) -> list[str]:
        return self.deliver(self._event(wamid, kind=TEXT, text=text))

    def tap(self, reply_id: str, title: str = "") -> list[str]:
        return self.deliver(self._event(None, kind=REPLY, reply_id=reply_id, text=title))

    def pin(self, lat: float, lon: float) -> list[str]:
        return self.deliver(self._event(None, kind=LOCATION, latitude=lat, longitude=lon))

    def photo(self) -> list[str]:
        return self.deliver(self._event(None, kind=MEDIA))

    @property
    def last(self) -> str:
        return self.client.sent[-1].body
