"""auth sessions, analyst role and incident location resolution

Revision ID: e5a7b3c9d1f2
Revises: c4e2a91b7d35
Create Date: 2026-11-05 09:00:00.000000

Phases 1-3 foundation:

* ``users.password_hash`` (nullable: existing users simply cannot sign in) and the new
  ``analyst`` role;
* ``user_sessions`` (hashed opaque session + CSRF tokens) and ``login_attempts``;
* location-resolution columns on ``incidents`` (status, precision, source, method,
  candidates, editor confirmation);
* an *additional* trigger: an approving review must name the incident's latest bulletin
  version. The existing approval/append-only triggers are left exactly as they are.

Everything is additive, so existing rows stay valid.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e5a7b3c9d1f2"
down_revision: Union[str, Sequence[str], None] = "c4e2a91b7d35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ROLES = "'admin', 'editor', 'contributor', 'service'"
NEW_ROLES = "'admin', 'editor', 'analyst', 'contributor', 'service'"
LOCATION_STATUSES = "'unresolved', 'ambiguous', 'resolved', 'editor_confirmed'"

LATEST_VERSION_FN = """
CREATE FUNCTION saferoutezw_require_latest_bulletin_version() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    latest uuid;
BEGIN
    IF NEW.decision = 'approved' THEN
        SELECT id INTO latest FROM bulletin_versions
        WHERE incident_id = NEW.incident_id
        ORDER BY version_number DESC LIMIT 1;
        -- A version of another incident is left to the composite foreign key to reject.
        IF latest IS DISTINCT FROM NEW.bulletin_version_id AND EXISTS (
            SELECT 1 FROM bulletin_versions
            WHERE id = NEW.bulletin_version_id AND incident_id = NEW.incident_id
        ) THEN
            RAISE EXCEPTION 'an approval must refer to the latest bulletin version of the incident'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
"""


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True,
                  comment="Argon2id hash; NULL means the account cannot sign in."))
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_role_valid"), "users", f"role IN ({NEW_ROLES})")

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_user_sessions_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_sessions_token_hash")),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email_lower", sa.Text(), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_attempts")),
    )
    op.create_index("ix_login_attempts_email_lower_attempted_at", "login_attempts", ["email_lower", "attempted_at"])
    op.create_index("ix_login_attempts_ip_address_attempted_at", "login_attempts", ["ip_address", "attempted_at"])

    op.add_column("incidents", sa.Column("location_status", sa.String(length=16),
                  server_default=sa.text("'unresolved'"), nullable=False))
    op.add_column("incidents", sa.Column("location_precision_m", sa.Float(), nullable=True))
    op.add_column("incidents", sa.Column("location_source", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("location_method", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("location_candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("incidents", sa.Column("location_note", sa.Text(), nullable=True))
    op.add_column("incidents", sa.Column("location_confirmed_by", sa.Uuid(), nullable=True))
    op.add_column("incidents", sa.Column("location_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("incidents", sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(op.f("fk_incidents_location_confirmed_by_users"), "incidents", "users",
                          ["location_confirmed_by"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint(op.f("ck_incidents_location_status_valid"), "incidents",
                               f"location_status IN ({LOCATION_STATUSES})")
    op.create_check_constraint(op.f("ck_incidents_location_precision_m_non_negative"), "incidents",
                               "location_precision_m IS NULL OR location_precision_m >= 0")

    op.execute(LATEST_VERSION_FN)
    op.execute(
        "CREATE TRIGGER trg_editorial_reviews_latest_bulletin_version BEFORE INSERT ON editorial_reviews "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_latest_bulletin_version()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_editorial_reviews_latest_bulletin_version ON editorial_reviews")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_latest_bulletin_version()")

    op.drop_constraint(op.f("ck_incidents_location_precision_m_non_negative"), "incidents", type_="check")
    op.drop_constraint(op.f("ck_incidents_location_status_valid"), "incidents", type_="check")
    op.drop_constraint(op.f("fk_incidents_location_confirmed_by_users"), "incidents", type_="foreignkey")
    for column in ("location_updated_at", "location_confirmed_at", "location_confirmed_by", "location_note",
                   "location_candidates", "location_method", "location_source", "location_precision_m",
                   "location_status"):
        op.drop_column("incidents", column)

    op.drop_table("login_attempts")
    op.drop_table("user_sessions")

    # Analysts cannot exist under the old vocabulary; they become read-only contributors.
    op.execute("UPDATE users SET role = 'contributor' WHERE role = 'analyst'")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_role_valid"), "users", f"role IN ({OLD_ROLES})")
    op.drop_column("users", "password_hash")
