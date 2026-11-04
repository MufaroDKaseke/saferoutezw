"""Authentication: sessions, cookies, CSRF, rate limiting, roles and user administration."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

import db_factories as f
from api_helpers import PASSWORD, make_login_user, sign_in
from app.core.security import sha256_hex, verify_password
from app.main import app
from app.models import AuditEvent, LoginAttempt, User, UserSession

pytestmark = pytest.mark.usefixtures("migrated_engine")

LOGIN = "/api/v1/auth/login"


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_login_sets_an_http_only_cookie_and_hides_the_token(client, session):
    user = make_login_user(session)
    session.commit()
    response = client.post(LOGIN, json={"email": user.email.upper(), "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == user.email and body["user"]["role"] == "editor"
    assert "password_hash" not in body["user"]
    cookie = response.headers["set-cookie"].lower()
    assert "srz_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    token = client.cookies.get("srz_session")
    assert token and token not in response.text  # never in a body
    stored = session.scalar(select(UserSession))
    assert stored.token_hash == sha256_hex(token) and token not in (stored.token_hash, stored.csrf_hash)
    assert body["csrf_token"] and body["csrf_token"] != token


def test_wrong_password_and_unknown_user_look_the_same(client, session):
    user = make_login_user(session)
    session.commit()
    bad = client.post(LOGIN, json={"email": user.email, "password": "wrong-password-123"})
    unknown = client.post(LOGIN, json={"email": "nobody@example.test", "password": "wrong-password-123"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json() and error_code(bad) == "INVALID_CREDENTIALS"
    assert "set-cookie" not in bad.headers


def test_inactive_users_and_users_without_a_password_cannot_sign_in(client, session):
    inactive = make_login_user(session, is_active=False)
    no_password = f.make_user(session)
    session.commit()
    assert client.post(LOGIN, json={"email": inactive.email, "password": PASSWORD}).status_code == 401
    assert client.post(LOGIN, json={"email": no_password.email, "password": PASSWORD}).status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client, session, settings):
    user = make_login_user(session)
    session.commit()
    for _ in range(settings.login_max_failures):
        assert client.post(LOGIN, json={"email": user.email, "password": "wrong-password-123"}).status_code == 401
    blocked = client.post(LOGIN, json={"email": user.email, "password": PASSWORD})  # even the right one
    assert blocked.status_code == 429 and error_code(blocked) == "RATE_LIMITED"
    assert "retry-after" in blocked.headers
    assert session.scalar(select(LoginAttempt).where(LoginAttempt.succeeded.is_(True))) is None


def test_me_requires_a_session_and_returns_the_csrf_token(client, session):
    assert client.get("/api/v1/auth/me").status_code == 401
    user, headers = sign_in(client, session)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["user"]["id"] == str(user.id)
    assert me.json()["csrf_token"] == headers["X-CSRF-Token"]
    assert me.headers["cache-control"] == "no-store"


def test_logout_revokes_the_session(client, session):
    _, headers = sign_in(client, session)
    token = client.cookies.get("srz_session")
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    session.expire_all()
    assert session.scalar(select(UserSession).where(UserSession.token_hash == sha256_hex(token))).revoked_at
    client.cookies.set("srz_session", token)  # replaying the old cookie must not work
    assert client.get("/api/v1/auth/me").status_code == 401


def test_state_changing_requests_need_the_csrf_token(client, session):
    sign_in(client, session)
    missing = client.post("/api/v1/auth/logout")
    wrong = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "nope"})
    assert missing.status_code == wrong.status_code == 403 and error_code(missing) == "CSRF_FAILED"


def test_foreign_origins_are_rejected(client, session):
    _, headers = sign_in(client, session)
    response = client.post("/api/v1/auth/logout", headers={**headers, "Origin": "https://evil.example"})
    assert response.status_code == 403
    login = client.post(LOGIN, json={"email": "a@b.co", "password": "x"}, headers={"Origin": "https://evil.example"})
    assert login.status_code == 403


def test_expired_and_absolute_limit_sessions_are_refused(client, session):
    sign_in(client, session)
    row = session.scalar(select(UserSession))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401

    row.expires_at = datetime.now(UTC) + timedelta(hours=1)
    session.execute(text("UPDATE user_sessions SET created_at = now() - interval '3 days'"))
    session.commit()
    session.expire_all()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_deactivating_a_user_ends_their_session(client, session):
    user, _ = sign_in(client, session)
    user.is_active = False
    session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_sliding_expiry_extends_an_active_session(client, session):
    sign_in(client, session)
    row = session.scalar(select(UserSession))
    row.last_seen_at = datetime.now(UTC) - timedelta(minutes=10)
    row.expires_at = datetime.now(UTC) + timedelta(minutes=5)
    session.commit()
    before = row.expires_at
    assert client.get("/api/v1/auth/me").status_code == 200
    session.refresh(row)
    assert row.expires_at > before


# --- error envelope --------------------------------------------------------------------------


def test_validation_errors_use_the_envelope_without_echoing_input(client):
    response = client.post(LOGIN, json={"email": "not-an-email", "password": "super-secret-value"})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_ERROR" and body["details"][0]["field"] == "email"
    assert "super-secret-value" not in response.text


def test_unknown_routes_use_the_envelope(client):
    response = client.get("/api/v1/nothing-here")
    assert response.status_code == 404 and error_code(response) == "NOT_FOUND"


# --- administration --------------------------------------------------------------------------


def test_only_admins_manage_users(client, session):
    _, headers = sign_in(client, session, "editor")
    assert client.get("/api/v1/admin/users").status_code == 403
    payload = {"email": "new@example.test", "display_name": "New", "role": "analyst", "password": PASSWORD}
    assert client.post("/api/v1/admin/users", json=payload, headers=headers).status_code == 403


def test_admin_creates_updates_and_revokes_users(client, session):
    _, headers = sign_in(client, session, "admin")
    payload = {"email": "Analyst@Example.test", "display_name": "An Analyst", "role": "analyst", "password": PASSWORD}
    created = client.post("/api/v1/admin/users", json=payload, headers=headers)
    assert created.status_code == 201 and created.json()["email"] == "analyst@example.test"
    assert "password" not in created.text
    new_id = created.json()["id"]
    stored = session.get(User, new_id)
    assert stored.password_hash.startswith("$argon2id$") and verify_password(PASSWORD, stored.password_hash)

    assert client.post("/api/v1/admin/users", json=payload, headers=headers).status_code == 409
    weak = {**payload, "email": "w@example.test", "password": "short"}
    assert error_code(client.post("/api/v1/admin/users", json=weak, headers=headers)) == "WEAK_PASSWORD"

    listing = client.get("/api/v1/admin/users", params={"page_size": 1})
    assert listing.json()["page_size"] == 1 and listing.json()["total"] == 2
    assert client.get("/api/v1/admin/users", params={"page_size": 1000}).status_code == 422

    patched = client.patch(f"/api/v1/admin/users/{new_id}", json={"role": "editor"}, headers=headers)
    assert patched.status_code == 200 and patched.json()["role"] == "editor"

    # The new user signs in elsewhere; the admin revokes that session.
    other = TestClient(app)
    assert other.post(LOGIN, json={"email": "analyst@example.test", "password": PASSWORD}).status_code == 200
    revoked = client.post(f"/api/v1/admin/users/{new_id}/sessions/revoke", headers=headers)
    assert revoked.json() == {"revoked": 1}
    assert other.get("/api/v1/auth/me").status_code == 401

    actions = {e.action for e in session.scalars(select(AuditEvent))}
    assert {"user.created", "user.updated", "user.sessions_revoked", "auth.login"} <= actions


def test_admin_cannot_lock_themselves_out(client, session):
    admin, headers = sign_in(client, session, "admin")
    for body in ({"is_active": False}, {"role": "editor"}):
        response = client.patch(f"/api/v1/admin/users/{admin.id}", json=body, headers=headers)
        assert response.status_code == 409


def test_changing_a_role_signs_the_user_out(client, session):
    _, headers = sign_in(client, session, "admin")
    victim = make_login_user(session, "editor")
    session.commit()
    other = TestClient(app)
    assert other.post(LOGIN, json={"email": victim.email, "password": PASSWORD}).status_code == 200
    client.patch(f"/api/v1/admin/users/{victim.id}", json={"role": "analyst"}, headers=headers)
    assert other.get("/api/v1/auth/me").status_code == 401


def test_health_stays_public(client):
    assert client.get("/health").status_code == 200
