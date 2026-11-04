"""Message templates for proactive (business-initiated) WhatsApp messages.

A business may only start a conversation, or write after the 24-hour customer-service window has
closed, with a template that Meta has *approved*. Which category Meta assigns to a road-safety
alert is Meta's decision, not ours: register the template in WhatsApp Manager, wait for approval,
then set ``WHATSAPP_ALERT_TEMPLATE_NAME`` / ``WHATSAPP_ALERT_TEMPLATE_LANGUAGE``. Until a name is
configured the bot sends alerts as session text only, which Meta will refuse outside the window
(the delivery is then recorded as failed, never silently dropped).

The template body this code expects has ONE variable:

    {{1}}

``{{1}}`` receives the whole alert text from ``alert_notifications._message`` (headline, place, link
and "Reply STOP to unsubscribe."), so the template body should not repeat any of that.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class AlertTemplate:
    name: str
    language: str


def alert_template(settings: Settings) -> AlertTemplate | None:
    if not settings.whatsapp_alert_template_name:
        return None
    return AlertTemplate(settings.whatsapp_alert_template_name, settings.whatsapp_alert_template_language)
