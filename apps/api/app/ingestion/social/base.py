"""Platform-neutral types for social collection.

A *platform adapter* knows one platform's Actor: what input to send, and how to judge and
normalise each returned item. Adapters are pure (no network, no database), so every
allowlist rule is unit-testable. ``poller`` does the I/O.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.ingestion.normalized import NormalizedReport


@dataclass(frozen=True)
class SocialSourceRef:
    """One allow-listed account, detached from any database session."""

    source_id: uuid.UUID
    name: str
    platform: str
    account_url: str
    platform_account_id: str | None
    actor_id: str
    enabled: bool
    poll_interval_seconds: int
    max_posts_per_run: int
    last_polled_at: datetime | None
    last_success_at: datetime | None
    last_post_id: str | None
    last_post_at: datetime | None
    collection_status: str


# What to do with one item the Actor returned.
ACCEPT = "accept"
REJECT = "reject"  # demonstrably another account's content: dropped, only counted
QUARANTINE = "quarantine"  # origin cannot be confirmed: kept aside for a human, never processed
IGNORE = "ignore"  # nothing to collect (no text, an Actor status row, ...)


@dataclass(frozen=True)
class Verdict:
    action: str
    reason: str | None = None
    report: NormalizedReport | None = None
    external_id: str | None = None
    post_url: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)  # small summary kept with quarantined items
    learned_account_id: str | None = None  # an id confirmed against the configured URL


@dataclass(frozen=True)
class Notice:
    """A status row from the Actor ("this Page is not visible", "blocked", ...)."""

    reason: str
    message: str
    blocking: bool  # the account itself could not be read


class PlatformAdapter(Protocol):
    platform: str

    def build_input(self, source: SocialSourceRef, *, since_hours: int) -> dict[str, Any]:
        """Actor input restricted to this one account and its newest posts."""

    def max_items(self, source: SocialSourceRef) -> int:
        """Hard cap on rows the Actor may return in a run."""

    def notice(self, item: dict[str, Any]) -> Notice | None:
        """A status row, or None for a post."""

    def judge(self, item: dict[str, Any], source: SocialSourceRef, *, max_chars: int) -> Verdict:
        """Validate origin and normalise one post."""
