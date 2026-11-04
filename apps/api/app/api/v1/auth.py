"""Sign-in, sign-out and the current session."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from app.api.deps import AppSettings, CurrentAuth, DbSession, check_origin
from app.api.errors import ERROR_RESPONSES, ErrorResponse
from app.core.security import csrf_token_for
from app.schemas.auth import LoginRequest, SessionOut, UserOut
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, settings, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


@router.post(
    "/login",
    response_model=SessionOut,
    responses={401: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
)
def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession, settings: AppSettings
) -> SessionOut:
    check_origin(request, settings)
    ip = request.client.host if request.client else None
    user, token = auth_service.login(
        db,
        settings,
        email=body.email,
        password=body.password,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
    )
    found = auth_service.find_active_session(db, settings, token)
    assert found is not None  # just created
    _set_cookie(response, settings, token)
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        user=UserOut.model_validate(user),
        csrf_token=csrf_token_for(token),
        expires_at=found[0].expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=ERROR_RESPONSES)
def logout(auth: CurrentAuth, response: Response, db: DbSession, settings: AppSettings) -> None:
    auth_service.revoke_session(db, auth.session, actor_id=auth.user.id)
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.get("/me", response_model=SessionOut, responses=ERROR_RESPONSES)
def me(auth: CurrentAuth, response: Response) -> SessionOut:
    response.headers["Cache-Control"] = "no-store"
    return SessionOut(
        user=UserOut.model_validate(auth.user),
        csrf_token=auth.csrf_token,
        expires_at=auth.session.expires_at,
    )
