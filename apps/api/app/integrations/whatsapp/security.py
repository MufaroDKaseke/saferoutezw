"""Webhook authenticity for the WhatsApp Cloud API.

Meta signs every POST with ``X-Hub-Signature-256: sha256=<hex HMAC of the raw body>`` using the
app secret. The signature must be checked against the *raw bytes* received, before any JSON
parsing, and compared in constant time.
"""

from __future__ import annotations

import hashlib
import hmac

SIGNATURE_PREFIX = "sha256="


def compute_signature(raw_body: bytes, app_secret: str) -> str:
    return SIGNATURE_PREFIX + hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes, header: str | None, app_secret: str | None) -> bool:
    """True only for a well-formed header whose HMAC matches. Never raises."""
    if not app_secret or not header or not header.startswith(SIGNATURE_PREFIX):
        return False
    return hmac.compare_digest(compute_signature(raw_body, app_secret), header.strip())


def verify_challenge(mode: str | None, token: str | None, expected_token: str | None) -> bool:
    """The GET handshake Meta performs when a webhook is subscribed."""
    if mode != "subscribe" or not token or not expected_token:
        return False
    return hmac.compare_digest(token.encode(), expected_token.encode())
