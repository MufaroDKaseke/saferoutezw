"""Request dependencies: database session, authenticated user, role checks, CSRF."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.errors import ApiError, forbidden, unauthenticated
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import constant_time_equal, csrf_token_for
from app.models import User, UserSession
from app.models.enums import UserRole
from app.services.auth import find_active_session

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"

READ_ROLES = (UserRole.ADMIN, UserRole.EDITOR, UserRole.ANALYST)
EDITOR_ROLES = (UserRole.ADMIN, UserRole.EDITOR)
ADMIN_ROLES = (UserRole.ADMIN,)


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession
    csrf_token: str


def trusted_origins(settings: Settings) -> set[str]:
    return {o.strip().rstrip("/") for o in settings.trusted_origins.split(",") if o.strip()}


def check_origin(request: Request, settings: Settings) -> None:
    """A browser-sent Origin must be one of ours. Requests without Origin (scripts) pass."""
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in trusted_origins(settings):
        raise forbidden("The request origin is not allowed.")


def get_auth(request: Request, db: DbSession, settings: AppSettings) -> AuthContext:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise unauthenticated()
    found = find_active_session(db, settings, token)
    if found is None:
        raise unauthenticated("Your session has expired. Sign in again.")
    user_session, user = found

    csrf_token = csrf_token_for(token)
    if request.method not in SAFE_METHODS:
        check_origin(request, settings)
        supplied = request.headers.get(CSRF_HEADER, "")
        if not supplied or not constant_time_equal(supplied, csrf_token):
            raise ApiError(403, "CSRF_FAILED", "The request could not be verified. Reload the page.")
    return AuthContext(user=user, session=user_session, csrf_token=csrf_token)


CurrentAuth = Annotated[AuthContext, Depends(get_auth)]


def require_roles(*roles: UserRole) -> Callable[..., AuthContext]:
    allowed = {r.value for r in roles}

    def dependency(auth: CurrentAuth) -> AuthContext:
        if auth.user.role not in allowed:
            raise forbidden()
        return auth

    return dependency


# Use as route-parameter annotations: ``auth: Reader``.
Reader = Annotated[AuthContext, Depends(require_roles(*READ_ROLES))]
Editor = Annotated[AuthContext, Depends(require_roles(*EDITOR_ROLES))]
Admin = Annotated[AuthContext, Depends(require_roles(*ADMIN_ROLES))]
