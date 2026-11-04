"""Helpers for API tests: users with a known password and signed-in clients."""

from __future__ import annotations

from app.core.security import hash_password

import db_factories as f

PASSWORD = "correct horse battery staple"
_HASH = hash_password(PASSWORD)  # hashed once: Argon2 is deliberately slow


def make_login_user(session, role: str = "editor", is_active: bool = True):
    user = f.make_user(session, role=role, is_active=is_active)
    user.password_hash = _HASH
    session.flush()
    return user


def sign_in(client, session, role: str = "editor"):
    """Create a user, sign them in, return (user, headers carrying the CSRF token)."""
    user = make_login_user(session, role)
    session.commit()
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return user, {"X-CSRF-Token": response.json()["csrf_token"]}
