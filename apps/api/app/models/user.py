"""Application users and editorial permissions (no credentials are stored)."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import UserRole, check_in
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person or service account.

    Only active users with the ``admin`` or ``editor`` role may record editorial
    decisions. ``service`` accounts (e.g. the AI pipeline) can author drafts but
    can never review or approve. Authentication is out of scope for this table.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(check_in("role", UserRole), name="role_valid"),
        CheckConstraint(r"email ~ '^[^@\s]+@[^@\s]+$'", name="email_format"),
        Index("ix_users_role_is_active", "role", "is_active"),
    )


# Case-insensitive email uniqueness without needing the citext extension.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
