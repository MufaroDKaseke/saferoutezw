"""Which platforms can actually be collected.

Only platforms with an adapter here can be enabled. X and TikTok are deliberately absent:
no suitable, verified Actor has been chosen for them (see docs/social-ingestion.md for what
enabling one takes). A source configured for them stays disabled and is never polled.
"""

from __future__ import annotations

from app.ingestion.social.base import PlatformAdapter
from app.ingestion.social.facebook import FacebookAdapter

ADAPTERS: dict[str, PlatformAdapter] = {FacebookAdapter.platform: FacebookAdapter()}


def get_adapter(platform: str) -> PlatformAdapter | None:
    return ADAPTERS.get(platform)
