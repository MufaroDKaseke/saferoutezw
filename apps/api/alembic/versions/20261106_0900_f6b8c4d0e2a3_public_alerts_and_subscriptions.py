"""public alert geography labels and phone alert subscriptions

Revision ID: f6b8c4d0e2a3
Revises: e5a7b3c9d1f2
Create Date: 2026-11-06 09:00:00.000000

Additive only:

* ``public_alerts.province`` / ``road_name`` / ``withdrawn_at``;
* subscriber tables (encrypted phone, keyed digest, hashed codes, consent evidence,
  management tokens) and ``subscriber_deliveries`` (per-recipient idempotent queue).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f6b8c4d0e2a3"
down_revision: Union[str, Sequence[str], None] = "e5a7b3c9d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("now()")
UUID_DEFAULT = sa.text("gen_random_uuid()")


def _id() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=UUID_DEFAULT, nullable=False)


def _created() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False)


def upgrade() -> None:
    op.add_column("public_alerts", sa.Column("province", sa.String(length=32), nullable=True))
    op.add_column("public_alerts", sa.Column("road_name", sa.Text(), nullable=True))
    op.add_column("public_alerts", sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "alert_subscribers",
        _id(),
        sa.Column("phone_ciphertext", sa.Text(), nullable=False),
        sa.Column("phone_digest", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unsubscribed_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_subscribers")),
        sa.UniqueConstraint("phone_digest", name=op.f("uq_alert_subscribers_phone_digest")),
        sa.CheckConstraint("channel IN ('sms', 'whatsapp')", name=op.f("ck_alert_subscribers_channel_valid")),
        sa.CheckConstraint("status IN ('pending', 'active', 'unsubscribed')", name=op.f("ck_alert_subscribers_status_valid")),
        sa.CheckConstraint("status <> 'active' OR verified_at IS NOT NULL", name=op.f("ck_alert_subscribers_active_requires_verification")),
    )
    op.create_index("ix_alert_subscribers_status_channel", "alert_subscribers", ["status", "channel"])

    op.create_table(
        "subscription_preferences",
        _id(),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("all_zimbabwe", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("provinces", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("corridors", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_preferences")),
        sa.ForeignKeyConstraint(["subscriber_id"], ["alert_subscribers.id"], name=op.f("fk_subscription_preferences_subscriber_id_alert_subscribers"), ondelete="CASCADE"),
        sa.UniqueConstraint("subscriber_id", name=op.f("uq_subscription_preferences_subscriber_id")),
    )

    op.create_table(
        "subscription_challenges",
        _id(),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_challenges")),
        sa.ForeignKeyConstraint(["subscriber_id"], ["alert_subscribers.id"], name=op.f("fk_subscription_challenges_subscriber_id_alert_subscribers"), ondelete="CASCADE"),
        sa.CheckConstraint("purpose IN ('activate', 'manage')", name=op.f("ck_subscription_challenges_purpose_valid")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_subscription_challenges_attempts_non_negative")),
    )
    op.create_index("ix_subscription_challenges_subscriber_id_created_at", "subscription_challenges", ["subscriber_id", "created_at"])

    op.create_table(
        "subscription_consents",
        _id(),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("consent_text_version", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("ip_digest", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_consents")),
        sa.ForeignKeyConstraint(["subscriber_id"], ["alert_subscribers.id"], name=op.f("fk_subscription_consents_subscriber_id_alert_subscribers"), ondelete="CASCADE"),
        sa.CheckConstraint("channel IN ('sms', 'whatsapp')", name=op.f("ck_subscription_consents_channel_valid")),
    )
    op.create_index("ix_subscription_consents_subscriber_id", "subscription_consents", ["subscriber_id"])

    op.create_table(
        "subscription_tokens",
        _id(),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscription_tokens")),
        sa.ForeignKeyConstraint(["subscriber_id"], ["alert_subscribers.id"], name=op.f("fk_subscription_tokens_subscriber_id_alert_subscribers"), ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_subscription_tokens_token_hash")),
    )
    op.create_index("ix_subscription_tokens_subscriber_id", "subscription_tokens", ["subscriber_id"])

    op.create_table(
        "subscriber_deliveries",
        _id(),
        sa.Column("public_alert_id", sa.Uuid(), nullable=False),
        sa.Column("subscriber_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=32), nullable=True),
        sa.Column("provider_reference", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=NOW, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        _created(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_subscriber_deliveries")),
        sa.ForeignKeyConstraint(["public_alert_id"], ["public_alerts.id"], name=op.f("fk_subscriber_deliveries_public_alert_id_public_alerts"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["alert_subscribers.id"], name=op.f("fk_subscriber_deliveries_subscriber_id_alert_subscribers"), ondelete="RESTRICT"),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_subscriber_deliveries_idempotency_key")),
        sa.CheckConstraint("channel IN ('sms', 'whatsapp')", name=op.f("ck_subscriber_deliveries_channel_valid")),
        sa.CheckConstraint("status IN ('queued', 'sent', 'delivered', 'failed', 'unknown')", name=op.f("ck_subscriber_deliveries_status_valid")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_subscriber_deliveries_attempts_non_negative")),
    )
    op.create_index("ix_subscriber_deliveries_status_next_attempt_at", "subscriber_deliveries", ["status", "next_attempt_at"])
    op.create_index("ix_subscriber_deliveries_public_alert_id", "subscriber_deliveries", ["public_alert_id"])
    op.create_index("ix_subscriber_deliveries_subscriber_id", "subscriber_deliveries", ["subscriber_id"])


def downgrade() -> None:
    op.drop_table("subscriber_deliveries")
    op.drop_table("subscription_tokens")
    op.drop_table("subscription_consents")
    op.drop_table("subscription_challenges")
    op.drop_table("subscription_preferences")
    op.drop_table("alert_subscribers")
    op.drop_column("public_alerts", "withdrawn_at")
    op.drop_column("public_alerts", "road_name")
    op.drop_column("public_alerts", "province")
