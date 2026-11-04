"""Password hashing and opaque token helpers.

Passwords use Argon2id. Session and CSRF tokens are random opaque strings; only their
SHA-256 digests are stored. The CSRF token is derived from the session token so a page
reload can recover it from ``/auth/me`` without storing it in plain text.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_PASSWORD_LENGTH = 12

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
# Verified against when the e-mail is unknown, so response time does not reveal which
# addresses exist.
_DUMMY_HASH = _hasher.hash("saferoutezw-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return password_hash is not None


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_policy_problem(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 256:
        return "Use at most 256 characters."
    return None


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token_for(session_token: str) -> str:
    return hashlib.sha256(b"saferoutezw-csrf:" + session_token.encode()).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
