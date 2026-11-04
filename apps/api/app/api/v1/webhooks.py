"""Inbound webhooks from external platforms (currently the WhatsApp Cloud API).

The WhatsApp endpoint authenticates Meta, not a user: it is not behind the session login, and
every POST must carry a valid ``X-Hub-Signature-256`` computed over the raw body. A valid request
is stored and acknowledged immediately; all processing happens later in the worker.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from app.api.deps import AppSettings, DbSession
from app.api.errors import ERROR_RESPONSES, ApiError
from app.integrations.whatsapp.messages import parse_webhook
from app.integrations.whatsapp.security import verify_challenge, verify_signature
from app.services.whatsapp.inbox import store_webhook

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["webhooks"], responses=ERROR_RESPONSES)

MAX_BODY_BYTES = 1_000_000


def _require_enabled(settings: AppSettings) -> None:
    if not settings.whatsapp_enabled:
        raise ApiError(404, "NOT_FOUND", "Not found.")


@router.get("", response_class=PlainTextResponse, include_in_schema=False)
def verify_subscription(
    settings: AppSettings,
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    """Meta calls this once when the webhook is configured; echo the challenge if the token matches."""
    _require_enabled(settings)
    expected = settings.whatsapp_verify_token.get_secret_value() if settings.whatsapp_verify_token else None
    if not verify_challenge(mode, token, expected) or challenge is None:
        raise ApiError(403, "FORBIDDEN", "Verification failed.")
    return challenge


@router.post("", status_code=200)
async def receive(request: Request, db: DbSession, settings: AppSettings) -> dict[str, str]:
    """Verify the signature, store the messages, answer 200. No business logic runs here."""
    _require_enabled(settings)
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ApiError(413, "PAYLOAD_TOO_LARGE", "Request body too large.")
    secret = settings.whatsapp_app_secret.get_secret_value() if settings.whatsapp_app_secret else None
    if not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), secret):
        log.warning("WhatsApp webhook rejected: bad or missing signature")
        raise ApiError(401, "INVALID_SIGNATURE", "Invalid signature.")
    try:
        body = json.loads(raw)
    except ValueError:
        raise ApiError(400, "INVALID_JSON", "Body is not valid JSON.") from None
    if not isinstance(body, dict):
        raise ApiError(400, "INVALID_JSON", "Body must be a JSON object.")

    parsed = parse_webhook(body)
    result = await run_in_threadpool(store_webhook, db, settings, parsed)
    log.info(
        "WhatsApp webhook: stored=%d duplicates=%d rate_limited=%d statuses=%d",
        result.stored, result.duplicates, result.rate_limited, result.statuses,
    )
    return {"status": "ok"}
