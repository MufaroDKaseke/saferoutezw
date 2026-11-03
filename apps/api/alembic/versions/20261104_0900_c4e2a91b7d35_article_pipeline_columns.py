"""article pipeline columns

Revision ID: c4e2a91b7d35
Revises: 7ba24614c7eb
Create Date: 2026-11-04 09:00:00.000000

Adds what the RSS -> full article -> redaction -> AI extraction pipeline needs:

* ``source_items``: redacted full article text, fetch status/error/time, a content
  hash (syndicated copies), the keyword-screen reason, and four new
  ``processing_status`` values (filtered, screened, fetched, fetch_failed);
* ``extraction_runs``: prompt version, token counts and completion time.

All new columns are nullable, so existing rows stay valid. Nothing here touches the
human-approval triggers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c4e2a91b7d35"
down_revision: Union[str, Sequence[str], None] = "7ba24614c7eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUSES = "'pending', 'processing', 'processed', 'failed', 'discarded'"
NEW_STATUSES = OLD_STATUSES + ", 'filtered', 'screened', 'fetched', 'fetch_failed'"
STATUS_CK = "ck_source_items_processing_status_valid"


def upgrade() -> None:
    op.add_column("source_items", sa.Column("article_text_redacted", sa.Text(), nullable=True,
                  comment="Full article text after privacy redaction; the only text sent to the AI."))
    op.add_column("source_items", sa.Column("fetch_status", sa.String(length=16), nullable=True))
    op.add_column("source_items", sa.Column("fetch_error", sa.Text(), nullable=True))
    op.add_column("source_items", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("source_items", sa.Column("content_hash", sa.String(length=64), nullable=True,
                  comment="SHA-256 of article_text_redacted; detects syndicated copies."))
    op.add_column("source_items", sa.Column("screen_reason", sa.Text(), nullable=True,
                  comment="Keyword screen outcome, e.g. matched terms or why it was filtered."))
    op.create_check_constraint(
        op.f("ck_source_items_fetch_status_valid"), "source_items",
        "fetch_status IS NULL OR fetch_status IN ('ok', 'failed')",
    )
    op.create_index("ix_source_items_content_hash", "source_items", ["content_hash"], unique=False)

    op.drop_constraint(op.f(STATUS_CK), "source_items", type_="check")
    op.create_check_constraint(op.f(STATUS_CK), "source_items", f"processing_status IN ({NEW_STATUSES})")

    op.add_column("extraction_runs", sa.Column("prompt_version", sa.Text(), nullable=True))
    op.add_column("extraction_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("extraction_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("extraction_runs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("extraction_runs", "completed_at")
    op.drop_column("extraction_runs", "output_tokens")
    op.drop_column("extraction_runs", "input_tokens")
    op.drop_column("extraction_runs", "prompt_version")

    # Map the new states onto the old vocabulary before the narrower CHECK returns.
    op.execute("UPDATE source_items SET processing_status = 'discarded' WHERE processing_status = 'filtered'")
    op.execute("UPDATE source_items SET processing_status = 'pending' WHERE processing_status IN ('screened', 'fetched')")
    op.execute("UPDATE source_items SET processing_status = 'failed' WHERE processing_status = 'fetch_failed'")
    op.drop_constraint(op.f(STATUS_CK), "source_items", type_="check")
    op.create_check_constraint(op.f(STATUS_CK), "source_items", f"processing_status IN ({OLD_STATUSES})")

    op.drop_index("ix_source_items_content_hash", table_name="source_items")
    op.drop_constraint(op.f("ck_source_items_fetch_status_valid"), "source_items", type_="check")
    for column in ("screen_reason", "content_hash", "fetched_at", "fetch_error", "fetch_status", "article_text_redacted"):
        op.drop_column("source_items", column)
