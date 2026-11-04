"""social media sources: allowlist table and quarantine

Revision ID: a7c9d1e3f5b2
Revises: f6b8c4d0e2a3
Create Date: 2026-11-07 09:00:00.000000

Additive only: ``social_sources`` (one row per allow-listed account, 1:1 with a ``sources``
row of kind 'social') and ``social_quarantine`` (posts whose origin could not be confirmed).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a7c9d1e3f5b2"
down_revision: Union[str, Sequence[str], None] = "f6b8c4d0e2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "social_sources",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("account_url", sa.Text(), nullable=False, comment="Canonical Page / account URL."),
        sa.Column("platform_account_id", sa.Text(), nullable=True,
                  comment="Platform's own id for the account; once known, posts must carry it."),
        sa.Column("actor_id", sa.Text(), nullable=False, comment="Apify Actor, e.g. owner/name."),
        sa.Column("max_posts_per_run", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_post_id", sa.Text(), nullable=True, comment="Newest post accepted so far (cursor)."),
        sa.Column("last_post_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collection_status", sa.String(length=16), server_default=sa.text("'idle'"), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name=op.f("fk_social_sources_source_id_sources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_sources")),
        sa.UniqueConstraint("source_id", name=op.f("uq_social_sources_source_id")),
        sa.UniqueConstraint("platform", "account_url", name=op.f("uq_social_sources_platform_account_url")),
        sa.CheckConstraint("platform IN ('facebook', 'x', 'tiktok')", name=op.f("ck_social_sources_platform_valid")),
        sa.CheckConstraint("collection_status IN ('idle', 'ok', 'error', 'blocked')", name=op.f("ck_social_sources_collection_status_valid")),
        sa.CheckConstraint("max_posts_per_run BETWEEN 1 AND 100", name=op.f("ck_social_sources_max_posts_per_run_range")),
    )
    op.execute(
        "CREATE TRIGGER trg_social_sources_set_updated_at BEFORE UPDATE ON social_sources "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
    )
    op.create_table(
        "social_quarantine",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("post_url", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name=op.f("fk_social_quarantine_source_id_sources"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingestion_run_id"], ["ingestion_runs.id"], name=op.f("fk_social_quarantine_ingestion_run_id_ingestion_runs"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_quarantine")),
    )
    op.create_index("ix_social_quarantine_source_id_created_at", "social_quarantine", ["source_id", "created_at"])


def downgrade() -> None:
    op.drop_table("social_quarantine")
    op.drop_table("social_sources")
