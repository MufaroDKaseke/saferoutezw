"""WhatsApp notification provider (Meta Cloud API) for OTPs, opt-in confirmations and alerts.

Verification codes and opt-in confirmations are replies inside a conversation the user just
started, so they go out as session text. Alerts are business-initiated and usually fall outside
the 24-hour window, so they use the approved template named in ``WHATSAPP_ALERT_TEMPLATE_NAME``
(see ``app.integrations.whatsapp.templates``). With sending in mock mode nothing leaves the process.
"""

from __future__ import annotations

from app.core.config import Settings
from app.integrations.whatsapp.client import WhatsAppClient, build_client
from app.integrations.whatsapp.messages import image_message, text_message
from app.integrations.whatsapp.templates import alert_template
from app.services.notifications.base import SendResult


class WhatsAppMetaProvider:
    name = "whatsapp_meta"
    channel = "whatsapp"

    def __init__(self, settings: Settings, client: WhatsAppClient | None = None) -> None:
        self._settings = settings
        self._client = client or build_client(settings)

    @property
    def is_mock(self) -> bool:
        return self._client.is_mock

    @staticmethod
    def _wa_id(to_e164: str) -> str:
        return to_e164.lstrip("+")

    def send_verification(self, to_e164: str, code: str, *, idempotency_key: str) -> SendResult:
        minutes = max(1, self._settings.otp_ttl_seconds // 60)
        body = f"SafeRouteZW verification code: {code}. It expires in {minutes} minutes. Do not share it with anyone."
        return self._client.send(self._wa_id(to_e164), text_message(body))

    def send_optin_confirmation(self, to_e164: str, *, idempotency_key: str) -> SendResult:
        body = "✅ You are subscribed to SafeRouteZW road alerts. Reply STOP at any time to unsubscribe."
        return self._client.send(self._wa_id(to_e164), text_message(body))

    def send_alert(self, to_e164: str, text: str, *, idempotency_key: str, image: bytes | None = None) -> SendResult:
        template = alert_template(self._settings)
        if template is not None:
            # A text template cannot carry the map; an image-header template would need its own approval.
            return self._client.send_template(self._wa_id(to_e164), template.name, template.language, [" ".join(text.split())])
        if image is not None:
            return self._client.send(self._wa_id(to_e164), image_message(text, image))  # map + the alert as caption
        return self._client.send(self._wa_id(to_e164), text_message(text))
