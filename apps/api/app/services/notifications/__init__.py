"""Outbound notification providers."""

from __future__ import annotations

from app.core.config import Settings
from app.services.notifications.base import NotificationProvider, SendResult
from app.services.notifications.mock import MockNotificationProvider

__all__ = ["MockNotificationProvider", "NotificationProvider", "SendResult", "get_notification_provider"]

# One mock instance per channel per process, so messages sent by the API and the job can be inspected
# together in the local demo. Real providers would be built per call from credentials.
_MOCKS: dict[str, MockNotificationProvider] = {}


def get_notification_provider(settings: Settings, channel: str) -> NotificationProvider:
    if settings.notification_provider == "mock":
        return _MOCKS.setdefault(channel, MockNotificationProvider(channel=channel))
    if settings.notification_provider == "whatsapp_meta" and channel == "whatsapp":
        from app.services.notifications.whatsapp_meta import WhatsAppMetaProvider  # lazy: avoids an import cycle

        return WhatsAppMetaProvider(settings)
    raise RuntimeError("No real messaging provider is configured for this channel.")


def reset_mock_providers() -> None:
    _MOCKS.clear()
