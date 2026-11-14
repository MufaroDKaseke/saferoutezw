"""NUST FM radio bulletins: numbered revisions, pinned script versions, human decisions

Revision ID: f2c4e6a8b0d3
Revises: e1b3d5f7a9c2
Create Date: 2026-11-12 12:00:00.000000

Step 3 of the story-to-air workflow (docs/superpowers/specs/2026-11-12-newsroom-story-to-air-design.md):

* ``radio_bulletins`` (name, air time, target length, and ``approved_revision_id``: the single current
  approved revision), ``radio_bulletin_revisions`` (numbered; draft / pending_approval / approved /
  superseded / rejected), ``radio_bulletin_items`` (the running order, each story pinned to one script
  version) and ``radio_bulletin_decisions`` (immutable human approvals and rejections);
* guards in the database, not only the application: at most one approved and at most one open revision per
  bulletin (partial unique indexes); the approved pointer may only move to an approved revision that has an
  approving decision; a revision cannot be approved or rejected without a matching decision and can only move
  forward through the lifecycle; the items of a revision that has left draft cannot change; decisions are
  append-only and need an active human editor (the existing generic functions are reused).

Everything is additive. The stories migration (e1b3d5f7a9c2) must already be applied.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2c4e6a8b0d3"
down_revision: Union[str, Sequence[str], None] = "e1b3d5f7a9c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATES = "'draft', 'pending_approval', 'approved', 'superseded', 'rejected'"

# The approved pointer can only move to a revision that is approved and has an approving decision.
FN_REQUIRE_BULLETIN_APPROVAL = """
CREATE FUNCTION saferoutezw_require_bulletin_approval() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.approved_revision_id IS NOT NULL
       AND (TG_OP = 'INSERT' OR OLD.approved_revision_id IS DISTINCT FROM NEW.approved_revision_id) THEN
        IF NOT EXISTS (
            SELECT 1 FROM radio_bulletin_decisions d
            WHERE d.revision_id = NEW.approved_revision_id AND d.decision = 'approved'
        ) THEN
            RAISE EXCEPTION 'revision % has no approving decision, so it cannot be the approved revision of bulletin %',
                NEW.approved_revision_id, NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM radio_bulletin_revisions r
            WHERE r.id = NEW.approved_revision_id AND r.state = 'approved'
        ) THEN
            RAISE EXCEPTION 'revision % is not in the approved state', NEW.approved_revision_id
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$
"""

# A revision starts as a draft and only moves forward: draft -> pending_approval -> approved | rejected, and
# approved -> superseded. It cannot become approved or rejected without a matching human decision.
FN_GUARD_REVISION_STATE = """
CREATE FUNCTION saferoutezw_guard_revision_state() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN
            RAISE EXCEPTION 'a bulletin revision starts as a draft, not %', NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.state IS DISTINCT FROM OLD.state THEN
        IF NOT ((OLD.state = 'draft' AND NEW.state = 'pending_approval')
             OR (OLD.state = 'pending_approval' AND NEW.state IN ('approved', 'rejected'))
             OR (OLD.state = 'approved' AND NEW.state = 'superseded')) THEN
            RAISE EXCEPTION 'a bulletin revision cannot go from % to %', OLD.state, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
        IF NEW.state IN ('approved', 'rejected') AND NOT EXISTS (
            SELECT 1 FROM radio_bulletin_decisions d WHERE d.revision_id = NEW.id AND d.decision = NEW.state
        ) THEN
            RAISE EXCEPTION 'revision % cannot be % without a matching decision', NEW.id, NEW.state
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$fn$
"""

# Items can only change while their revision is a draft; an approved bulletin is never edited in place.
FN_FREEZE_BULLETIN_ITEMS = """
CREATE FUNCTION saferoutezw_freeze_bulletin_items() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    rev_state text;
BEGIN
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT state INTO rev_state FROM radio_bulletin_revisions WHERE id = OLD.revision_id;
        IF rev_state IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'the items of a % bulletin revision cannot change', COALESCE(rev_state, 'missing')
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT state INTO rev_state FROM radio_bulletin_revisions WHERE id = NEW.revision_id;
        IF rev_state IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'the items of a % bulletin revision cannot change', COALESCE(rev_state, 'missing')
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$fn$
"""


def _uuid_pk() -> sa.Column:
    return sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "radio_bulletins",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_seconds", sa.Integer(), nullable=False),
        sa.Column("approved_revision_id", sa.Uuid(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_radio_bulletins_name_not_blank")),
        sa.CheckConstraint(
            "target_seconds > 0 AND target_seconds <= 7200", name=op.f("ck_radio_bulletins_target_seconds_in_range")
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_radio_bulletins_created_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radio_bulletins")),
    )
    op.create_index("ix_radio_bulletins_scheduled_for", "radio_bulletins", ["scheduled_for"])
    op.create_index("ix_radio_bulletins_created_by", "radio_bulletins", ["created_by"])

    op.create_table(
        "radio_bulletin_revisions",
        _uuid_pk(),
        sa.Column("bulletin_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("submitted_by", sa.Uuid(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aired_by", sa.Uuid(), nullable=True),
        sa.Column("aired_at", sa.DateTime(timezone=True), nullable=True, comment="When it was marked as broadcast."),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint("revision_number >= 1", name=op.f("ck_radio_bulletin_revisions_revision_number_positive")),
        sa.CheckConstraint(f"state IN ({STATES})", name=op.f("ck_radio_bulletin_revisions_state_valid")),
        sa.CheckConstraint(
            "(submitted_by IS NULL) = (submitted_at IS NULL)", name=op.f("ck_radio_bulletin_revisions_submitted_by_and_at_together")
        ),
        sa.CheckConstraint(
            "(approved_by IS NULL) = (approved_at IS NULL)", name=op.f("ck_radio_bulletin_revisions_approved_by_and_at_together")
        ),
        sa.CheckConstraint(
            "(aired_by IS NULL) = (aired_at IS NULL)", name=op.f("ck_radio_bulletin_revisions_aired_by_and_at_together")
        ),
        sa.CheckConstraint(
            "state = 'draft' OR submitted_at IS NOT NULL", name=op.f("ck_radio_bulletin_revisions_only_drafts_are_unsubmitted")
        ),
        sa.CheckConstraint(
            "(state IN ('approved', 'superseded')) = (approved_at IS NOT NULL)",
            name=op.f("ck_radio_bulletin_revisions_approval_time_matches_state"),
        ),
        sa.CheckConstraint(
            "aired_at IS NULL OR approved_at IS NOT NULL", name=op.f("ck_radio_bulletin_revisions_only_approved_revisions_air")
        ),
        sa.ForeignKeyConstraint(["bulletin_id"], ["radio_bulletins.id"], name=op.f("fk_radio_bulletin_revisions_bulletin_id_radio_bulletins"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_radio_bulletin_revisions_created_by_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], name=op.f("fk_radio_bulletin_revisions_submitted_by_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], name=op.f("fk_radio_bulletin_revisions_approved_by_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["aired_by"], ["users.id"], name=op.f("fk_radio_bulletin_revisions_aired_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radio_bulletin_revisions")),
        sa.UniqueConstraint("bulletin_id", "revision_number", name="uq_radio_bulletin_revisions_bulletin_id_revision_number"),
        sa.UniqueConstraint("id", "bulletin_id", name="uq_radio_bulletin_revisions_id_bulletin_id"),
    )
    op.create_index(
        "uq_radio_bulletin_revisions_one_approved",
        "radio_bulletin_revisions",
        ["bulletin_id"],
        unique=True,
        postgresql_where=sa.text("state = 'approved'"),
    )
    op.create_index(
        "uq_radio_bulletin_revisions_one_open",
        "radio_bulletin_revisions",
        ["bulletin_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('draft', 'pending_approval')"),
    )
    op.create_index("ix_radio_bulletin_revisions_state", "radio_bulletin_revisions", ["state"])

    # The bulletin and its revisions point at each other, so this key is added once both tables exist.
    op.create_foreign_key(
        "fk_radio_bulletins_approved_revision_id_revisions",
        "radio_bulletins",
        "radio_bulletin_revisions",
        ["approved_revision_id", "id"],
        ["id", "bulletin_id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "radio_bulletin_items",
        _uuid_pk(),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.Uuid(), nullable=False),
        sa.Column("duration_override_seconds", sa.Integer(), nullable=True, comment="For a clip: replaces the reading-time estimate."),
        sa.Column("note", sa.Text(), nullable=True, comment="For the newsreader, for example the clip to play."),
        _now("created_at"),
        sa.CheckConstraint("position >= 1", name=op.f("ck_radio_bulletin_items_position_positive")),
        sa.CheckConstraint(
            "duration_override_seconds IS NULL OR (duration_override_seconds > 0 AND duration_override_seconds <= 3600)",
            name=op.f("ck_radio_bulletin_items_duration_override_in_range"),
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["radio_bulletin_revisions.id"], name=op.f("fk_radio_bulletin_items_revision_id_radio_bulletin_revisions"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], name=op.f("fk_radio_bulletin_items_story_id_stories"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["script_id", "story_id"],
            ["story_scripts.id", "story_scripts.story_id"],
            name="fk_radio_bulletin_items_script_id_story_scripts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radio_bulletin_items")),
        sa.UniqueConstraint("revision_id", "position", name="uq_radio_bulletin_items_revision_id_position"),
        sa.UniqueConstraint("revision_id", "story_id", name="uq_radio_bulletin_items_revision_id_story_id"),
    )
    op.create_index("ix_radio_bulletin_items_story_id", "radio_bulletin_items", ["story_id"])
    op.create_index("ix_radio_bulletin_items_script_id", "radio_bulletin_items", ["script_id"])

    op.create_table(
        "radio_bulletin_decisions",
        _uuid_pk(),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("self_approved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _now("decided_at"),
        sa.CheckConstraint("decision IN ('approved', 'rejected')", name=op.f("ck_radio_bulletin_decisions_decision_valid")),
        sa.CheckConstraint(
            "decision <> 'rejected' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name=op.f("ck_radio_bulletin_decisions_rejecting_needs_a_comment"),
        ),
        sa.CheckConstraint(
            "NOT self_approved OR decision = 'approved'", name=op.f("ck_radio_bulletin_decisions_self_approved_only_on_approval")
        ),
        sa.ForeignKeyConstraint(["revision_id"], ["radio_bulletin_revisions.id"], name="fk_radio_bulletin_decisions_revision_id_revisions", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name=op.f("fk_radio_bulletin_decisions_reviewer_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_radio_bulletin_decisions")),
    )
    op.create_index("ix_radio_bulletin_decisions_revision_id_decided_at", "radio_bulletin_decisions", ["revision_id", "decided_at"])
    op.create_index("ix_radio_bulletin_decisions_reviewer_id", "radio_bulletin_decisions", ["reviewer_id"])

    for table in ("radio_bulletins", "radio_bulletin_revisions"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
        )
    op.execute(
        "CREATE TRIGGER trg_radio_bulletin_decisions_append_only BEFORE UPDATE OR DELETE ON radio_bulletin_decisions "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_forbid_modification()"
    )
    op.execute(
        "CREATE TRIGGER trg_radio_bulletin_decisions_require_human_reviewer BEFORE INSERT ON radio_bulletin_decisions "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_human_reviewer()"
    )
    op.execute(FN_REQUIRE_BULLETIN_APPROVAL)
    op.execute(
        "CREATE TRIGGER trg_radio_bulletins_require_approval BEFORE INSERT OR UPDATE OF approved_revision_id ON radio_bulletins "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_bulletin_approval()"
    )
    op.execute(FN_GUARD_REVISION_STATE)
    op.execute(
        "CREATE TRIGGER trg_radio_bulletin_revisions_guard_state BEFORE INSERT OR UPDATE OF state ON radio_bulletin_revisions "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_guard_revision_state()"
    )
    op.execute(FN_FREEZE_BULLETIN_ITEMS)
    op.execute(
        "CREATE TRIGGER trg_radio_bulletin_items_freeze BEFORE INSERT OR UPDATE OR DELETE ON radio_bulletin_items "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_freeze_bulletin_items()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_radio_bulletin_items_freeze ON radio_bulletin_items")
    op.execute("DROP TRIGGER IF EXISTS trg_radio_bulletin_revisions_guard_state ON radio_bulletin_revisions")
    op.execute("DROP TRIGGER IF EXISTS trg_radio_bulletins_require_approval ON radio_bulletins")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_freeze_bulletin_items()")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_guard_revision_state()")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_bulletin_approval()")

    op.drop_constraint("fk_radio_bulletins_approved_revision_id_revisions", "radio_bulletins", type_="foreignkey")
    # Dropping a table drops its triggers with it.
    op.drop_table("radio_bulletin_decisions")
    op.drop_table("radio_bulletin_items")
    op.drop_table("radio_bulletin_revisions")
    op.drop_table("radio_bulletins")
