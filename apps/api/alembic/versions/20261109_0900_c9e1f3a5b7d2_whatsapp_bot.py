"""whatsapp bot: conversations, inbound queue, outbound log

Revision ID: c9e1f3a5b7d2
Revises: b8d0e2f4a6c1
Create Date: 2026-11-09 09:00:00.000000

Additive only. ``whatsapp_conversations`` (menu state, expires), ``whatsapp_inbound`` (received
messages, unique on Meta's message id, doubles as the durable work queue) and ``whatsapp_outbound``
(idempotent send log that correlates delivery receipts). Phone numbers are stored only as a keyed
digest plus Fernet ciphertext.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c9e1f3a5b7d2"
down_revision: Union[str, Sequence[str], None] = "b8d0e2f4a6c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("now()")
UUID_DEFAULT = sa.text("gen_random_uuid()")
EMPTY_JSON = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "whatsapp_conversations",
        sa.Column("id", sa.Uuid(), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("sender_digest", sa.String(length=64), nullable=False),
        sa.Column("sender_ciphertext", sa.Text(), nullable=False),
        sa.Column("flow", sa.String(length=32), server_default=sa.text("'menu'"), nullable=False),
        sa.Column("step", sa.String(length=32), server_default=sa.text("'start'"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default=EMPTY_JSON, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_conversations")),
        sa.UniqueConstraint("sender_digest", name=op.f("uq_whatsapp_conversations_sender_digest")),
    )
    op.execute(
        "CREATE TRIGGER trg_whatsapp_conversations_set_updated_at BEFORE UPDATE ON whatsapp_conversations "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
    )

    op.create_table(
        "whatsapp_inbound",
        sa.Column("id", sa.Uuid(), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("wamid", sa.Text(), nullable=False),
        sa.Column("sender_digest", sa.String(length=64), nullable=False),
        sa.Column("sender_ciphertext", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=EMPTY_JSON, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Timestamp WhatsApp gave the message."),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_inbound")),
        sa.UniqueConstraint("wamid", name=op.f("uq_whatsapp_inbound_wamid")),
        sa.CheckConstraint("status IN ('pending', 'processing', 'done', 'failed')",
                           name=op.f("ck_whatsapp_inbound_status_valid")),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_whatsapp_inbound_attempts_non_negative")),
    )
    op.create_index("ix_whatsapp_inbound_status_created_at", "whatsapp_inbound", ["status", "created_at"])

    op.create_table(
        "whatsapp_outbound",
        sa.Column("id", sa.Uuid(), server_default=UUID_DEFAULT, nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("sender_digest", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("provider_message_id", sa.Text(), nullable=True,
                  comment="Meta's id; correlates delivery receipts."),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_outbound")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_whatsapp_outbound_idempotency_key")),
        sa.CheckConstraint("status IN ('queued', 'sent', 'delivered', 'read', 'failed')",
                           name=op.f("ck_whatsapp_outbound_status_valid")),
    )
    op.execute(
        "CREATE TRIGGER trg_whatsapp_outbound_set_updated_at BEFORE UPDATE ON whatsapp_outbound "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
    )
    op.create_index("ix_whatsapp_outbound_provider_message_id", "whatsapp_outbound", ["provider_message_id"])


def downgrade() -> None:
    op.drop_table("whatsapp_outbound")
    op.drop_table("whatsapp_inbound")
    op.drop_table("whatsapp_conversations")
