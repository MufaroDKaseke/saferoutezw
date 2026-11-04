"""Request and response models for authentication and user administration."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.enums import UserRole

Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class LoginRequest(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class SessionOut(BaseModel):
    """The signed-in user plus the CSRF token to send as ``X-CSRF-Token`` on writes."""

    user: UserOut
    csrf_token: str
    expires_at: datetime


class CreateUserRequest(BaseModel):
    email: Email
    display_name: DisplayName
    role: UserRole
    password: str = Field(max_length=256)


class UpdateUserRequest(BaseModel):
    display_name: DisplayName | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, max_length=256)


class RevokedSessions(BaseModel):
    revoked: int
