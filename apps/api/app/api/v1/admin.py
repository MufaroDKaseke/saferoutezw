"""User administration (admin role only)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import Admin, DbSession
from app.api.errors import ERROR_RESPONSES, ApiError, conflict, not_found
from app.api.pagination import Page, Pagination, paginate
from app.core.security import hash_password, password_policy_problem
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import CreateUserRequest, RevokedSessions, UpdateUserRequest, UserOut
from app.services.audit import record_audit
from app.services.auth import normalise_email, revoke_user_sessions

router = APIRouter(prefix="/admin", tags=["admin"], responses=ERROR_RESPONSES)


def _password_or_422(password: str) -> str:
    problem = password_policy_problem(password)
    if problem:
        raise ApiError(422, "WEAK_PASSWORD", problem)
    return hash_password(password)


def _get_user(db, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("USER_NOT_FOUND", "The requested user was not found.")
    return user


@router.get("/users", response_model=Page[UserOut])
def list_users(auth: Admin, db: DbSession, pagination: Pagination) -> Page[UserOut]:
    query = select(User).order_by(func.lower(User.email), User.id)
    rows, total = paginate(db, query, pagination)
    return Page(
        items=[UserOut.model_validate(r[0]) for r in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserRequest, auth: Admin, db: DbSession) -> UserOut:
    user = User(
        email=normalise_email(body.email),
        display_name=body.display_name,
        role=body.role.value,
        password_hash=_password_or_422(body.password),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise conflict("EMAIL_IN_USE", "A user with this email already exists.") from None
    record_audit(
        db,
        actor_id=auth.user.id,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        details={"role": user.role},
    )
    db.commit()
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, body: UpdateUserRequest, auth: Admin, db: DbSession) -> UserOut:
    user = _get_user(db, user_id)
    changes: dict[str, object] = {}
    if user.id == auth.user.id and (
        body.is_active is False or (body.role is not None and body.role != UserRole.ADMIN)
    ):
        raise conflict("CANNOT_LOCK_YOURSELF_OUT", "You cannot deactivate or demote your own account.")
    if body.display_name is not None:
        user.display_name = body.display_name
        changes["display_name"] = True
    if body.role is not None and body.role.value != user.role:
        changes["role"] = {"from": user.role, "to": body.role.value}
        user.role = body.role.value
    if body.is_active is not None and body.is_active != user.is_active:
        changes["is_active"] = body.is_active
        user.is_active = body.is_active
    if body.password is not None:
        user.password_hash = _password_or_422(body.password)
        changes["password_changed"] = True
    if changes.get("password_changed") or changes.get("is_active") is False or "role" in changes:
        revoke_user_sessions(db, user.id)  # privileges changed: force a fresh sign-in
    record_audit(
        db,
        actor_id=auth.user.id,
        action="user.updated",
        entity_type="user",
        entity_id=user.id,
        details={"changes": list(changes)} if changes else {},
    )
    db.commit()
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/sessions/revoke", response_model=RevokedSessions)
def revoke_sessions(user_id: uuid.UUID, auth: Admin, db: DbSession) -> RevokedSessions:
    user = _get_user(db, user_id)
    count = revoke_user_sessions(db, user.id)
    record_audit(
        db,
        actor_id=auth.user.id,
        action="user.sessions_revoked",
        entity_type="user",
        entity_id=user.id,
        details={"count": count},
    )
    db.commit()
    return RevokedSessions(revoked=count)
