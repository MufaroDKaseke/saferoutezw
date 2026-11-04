"""Sign-in, server-side sessions and login rate limiting (PostgreSQL-backed)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.core.config import Settings
from app.core.security import (
    csrf_token_for,
    hash_password,
    new_session_token,
    password_needs_rehash,
    sha256_hex,
    verify_password,
)
from app.models import LoginAttempt, User, UserSession
from app.services.audit import record_audit

_TOUCH_AFTER = timedelta(seconds=60)


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _now() -> datetime:
    return datetime.now(UTC)


def _too_many_failures(session: Session, settings: Settings, email_lower: str, ip: str | None) -> bool:
    since = _now() - timedelta(minutes=settings.login_window_minutes)
    conditions = [LoginAttempt.email_lower == email_lower]
    if ip:
        conditions.append(LoginAttempt.ip_address == ip)
    failures = session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.succeeded.is_(False), LoginAttempt.attempted_at >= since, or_(*conditions))
    )
    return (failures or 0) >= settings.login_max_failures


def login(
    session: Session,
    settings: Settings,
    *,
    email: str,
    password: str,
    ip: str | None,
    user_agent: str | None,
) -> tuple[User, str]:
    """Check credentials and open a session. Returns the user and the raw session token."""
    email_lower = normalise_email(email)
    if _too_many_failures(session, settings, email_lower, ip):
        raise ApiError(
            429,
            "RATE_LIMITED",
            "Too many failed sign-in attempts. Try again later.",
            headers={"Retry-After": str(settings.login_window_minutes * 60)},
        )

    user = session.scalar(select(User).where(func.lower(User.email) == email_lower))
    password_ok = verify_password(password, user.password_hash if user else None)
    valid = bool(user and user.is_active and password_ok)

    now = _now()
    session.add(LoginAttempt(email_lower=email_lower, ip_address=ip, attempted_at=now, succeeded=valid))
    if not valid or user is None:
        session.commit()  # the failure must be counted even though the request errors
        raise ApiError(401, "INVALID_CREDENTIALS", "The email or password is incorrect.")

    if user.password_hash and password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    token = new_session_token()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=sha256_hex(token),
            csrf_hash=sha256_hex(csrf_token_for(token)),
            expires_at=now + timedelta(minutes=settings.session_ttl_minutes),
            last_seen_at=now,
            ip_address=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    record_audit(session, actor_id=user.id, action="auth.login", entity_type="user", entity_id=user.id)
    # Housekeeping: old attempts and dead sessions are of no use.
    session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=2)))
    session.commit()
    return user, token


def find_active_session(
    session: Session, settings: Settings, token: str
) -> tuple[UserSession, User] | None:
    """Resolve a session cookie to (session, user), sliding its expiry. None if invalid."""
    row = session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == sha256_hex(token))
    ).first()
    if row is None:
        return None
    user_session, user = row
    now = _now()
    absolute_end = user_session.created_at + timedelta(hours=settings.session_absolute_max_hours)
    if (
        user_session.revoked_at is not None
        or user_session.expires_at <= now
        or absolute_end <= now
        or not user.is_active
    ):
        return None
    if now - user_session.last_seen_at > _TOUCH_AFTER:
        user_session.last_seen_at = now
        user_session.expires_at = min(now + timedelta(minutes=settings.session_ttl_minutes), absolute_end)
        session.commit()
    return user_session, user


def revoke_session(session: Session, user_session: UserSession, *, actor_id: uuid.UUID) -> None:
    user_session.revoked_at = _now()
    record_audit(session, actor_id=actor_id, action="auth.logout", entity_type="user", entity_id=actor_id)
    session.commit()


def revoke_user_sessions(session: Session, user_id: uuid.UUID) -> int:
    """Revoke every live session of a user. Returns how many were revoked."""
    result = session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    return result.rowcount or 0
