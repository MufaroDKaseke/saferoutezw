"""NUST FM stories: reporter role, stories, immutable script versions and approval decisions

Revision ID: e1b3d5f7a9c2
Revises: d0f2a4c6e8b3
Create Date: 2026-11-12 09:00:00.000000

Step 1 of the story-to-air workflow (docs/superpowers/specs/2026-11-12-newsroom-story-to-air-design.md):

* widens ``ck_users_role_valid`` with the ``reporter`` role (pattern: e5a7b3c9d1f2);
* ``stories`` (optionally from an article; at most one open story per article), ``story_scripts``
  (immutable versions, AI metadata kept on the row) and ``story_reviews`` (immutable decisions pinned
  to one script version);
* database guards copied from the road-safety design: the generic append-only trigger on scripts and
  reviews, the human-reviewer trigger on reviews, and a stage guard so a story can only be ``approved``
  once its latest script has an approving review.

Everything is additive. The bulletin tables arrive with the bulletins step.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e1b3d5f7a9c2"
down_revision: Union[str, Sequence[str], None] = "d0f2a4c6e8b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ROLES = "'admin', 'editor', 'analyst', 'contributor', 'service'"
NEW_ROLES = "'admin', 'editor', 'analyst', 'reporter', 'contributor', 'service'"
STAGES = "'assigned', 'drafting', 'in_review', 'changes_requested', 'approved', 'broadcast', 'dropped'"

# A story can only become 'approved' when its newest script has an approving review, and only become
# 'broadcast' when some approved review exists. Inserting a story straight into either stage is refused.
FN_REQUIRE_STORY_APPROVAL = """
CREATE FUNCTION saferoutezw_require_story_approval() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.stage IN ('approved', 'broadcast')
       AND (TG_OP = 'INSERT' OR OLD.stage IS DISTINCT FROM NEW.stage) THEN
        IF NEW.stage = 'approved' THEN
            IF NOT EXISTS (
                SELECT 1
                FROM story_reviews r JOIN story_scripts s ON s.id = r.script_id
                WHERE r.story_id = NEW.id AND r.decision = 'approved'
                  AND s.version_number = (SELECT max(version_number) FROM story_scripts WHERE story_id = NEW.id)
            ) THEN
                RAISE EXCEPTION 'story % cannot be approved without an approving review of its latest script', NEW.id
                    USING ERRCODE = 'check_violation';
            END IF;
        ELSIF NOT EXISTS (SELECT 1 FROM story_reviews WHERE story_id = NEW.id AND decision = 'approved') THEN
            RAISE EXCEPTION 'story % cannot be broadcast without an approving review', NEW.id
                USING ERRCODE = 'check_violation';
        END IF;
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
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_role_valid"), "users", f"role IN ({NEW_ROLES})")

    op.create_table(
        "stories",
        _uuid_pk(),
        sa.Column("source_item_id", sa.Uuid(), nullable=True, comment="The article it came from, if any."),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=24), server_default=sa.text("'assigned'"), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True, comment="How the reporter checked the facts."),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.Uuid(), nullable=True),
        sa.Column("follows_story_id", sa.Uuid(), nullable=True, comment="The earlier story this one follows up."),
        _now("created_at"),
        _now("updated_at"),
        sa.CheckConstraint(f"stage IN ({STAGES})", name=op.f("ck_stories_stage_valid")),
        sa.CheckConstraint("length(btrim(title)) > 0", name=op.f("ck_stories_title_not_blank")),
        sa.CheckConstraint(
            "(verified_at IS NULL) = (verified_by IS NULL) AND (verified_at IS NULL) = (verification_note IS NULL)",
            name=op.f("ck_stories_verification_all_or_nothing"),
        ),
        sa.CheckConstraint(
            "verification_note IS NULL OR length(btrim(verification_note)) > 0",
            name=op.f("ck_stories_verification_note_not_blank"),
        ),
        sa.CheckConstraint(
            "follows_story_id IS NULL OR follows_story_id <> id", name=op.f("ck_stories_cannot_follow_itself")
        ),
        sa.ForeignKeyConstraint(["source_item_id"], ["source_items.id"], name=op.f("fk_stories_source_item_id_source_items"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], name=op.f("fk_stories_assignee_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by"], ["users.id"], name=op.f("fk_stories_verified_by_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["follows_story_id"], ["stories.id"], name=op.f("fk_stories_follows_story_id_stories"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stories")),
    )
    op.create_index(
        "uq_stories_one_open_story_per_article",
        "stories",
        ["source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL AND stage NOT IN ('broadcast', 'dropped')"),
    )
    op.create_index("ix_stories_assignee_id_stage", "stories", ["assignee_id", "stage"])
    op.create_index("ix_stories_stage_updated_at", "stories", ["stage", "updated_at"])
    op.create_index("ix_stories_source_item_id", "stories", ["source_item_id"])
    op.create_index("ix_stories_follows_story_id", "stories", ["follows_story_id"])

    op.create_table(
        "story_scripts",
        _uuid_pk(),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("headline", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("estimated_seconds", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), server_default=sa.text("'human'"), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        _now("created_at"),
        sa.CheckConstraint("version_number >= 1", name=op.f("ck_story_scripts_version_number_positive")),
        sa.CheckConstraint(
            "length(btrim(headline)) > 0 AND length(btrim(body)) > 0", name=op.f("ck_story_scripts_content_not_blank")
        ),
        sa.CheckConstraint("estimated_seconds >= 0", name=op.f("ck_story_scripts_estimated_seconds_non_negative")),
        sa.CheckConstraint("origin IN ('human', 'ai_draft')", name=op.f("ck_story_scripts_origin_valid")),
        sa.CheckConstraint(
            "origin = 'ai_draft' OR (model_name IS NULL AND prompt_version IS NULL "
            "AND input_tokens IS NULL AND output_tokens IS NULL)",
            name=op.f("ck_story_scripts_ai_metadata_only_on_ai_drafts"),
        ),
        sa.CheckConstraint(
            "(input_tokens IS NULL OR input_tokens >= 0) AND (output_tokens IS NULL OR output_tokens >= 0)",
            name=op.f("ck_story_scripts_tokens_non_negative"),
        ),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], name=op.f("fk_story_scripts_story_id_stories"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name=op.f("fk_story_scripts_created_by_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_scripts")),
        sa.UniqueConstraint("story_id", "version_number", name="uq_story_scripts_story_id_version_number"),
        sa.UniqueConstraint("id", "story_id", name="uq_story_scripts_id_story_id"),
    )
    op.create_index("ix_story_scripts_created_by", "story_scripts", ["created_by"])
    op.create_index("ix_story_scripts_origin_created_at", "story_scripts", ["origin", "created_at"])

    op.create_table(
        "story_reviews",
        _uuid_pk(),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("script_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("self_approved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        _now("reviewed_at"),
        sa.CheckConstraint("decision IN ('approved', 'changes_requested')", name=op.f("ck_story_reviews_decision_valid")),
        sa.CheckConstraint(
            "decision <> 'changes_requested' OR (comment IS NOT NULL AND length(btrim(comment)) > 0)",
            name=op.f("ck_story_reviews_sending_back_needs_a_comment"),
        ),
        sa.CheckConstraint(
            "NOT self_approved OR decision = 'approved'", name=op.f("ck_story_reviews_self_approved_only_on_approval")
        ),
        sa.ForeignKeyConstraint(["story_id"], ["stories.id"], name=op.f("fk_story_reviews_story_id_stories"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], name=op.f("fk_story_reviews_reviewer_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["script_id", "story_id"],
            ["story_scripts.id", "story_scripts.story_id"],
            name="fk_story_reviews_script_id_story_scripts",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_story_reviews")),
    )
    op.create_index("ix_story_reviews_story_id_reviewed_at", "story_reviews", ["story_id", "reviewed_at"])
    op.create_index("ix_story_reviews_script_id", "story_reviews", ["script_id"])
    op.create_index("ix_story_reviews_reviewer_id", "story_reviews", ["reviewer_id"])

    op.execute(
        "CREATE TRIGGER trg_stories_set_updated_at BEFORE UPDATE ON stories "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_set_updated_at()"
    )
    for table in ("story_scripts", "story_reviews"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION saferoutezw_forbid_modification()"
        )
    op.execute(
        "CREATE TRIGGER trg_story_reviews_require_human_reviewer BEFORE INSERT ON story_reviews "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_human_reviewer()"
    )
    op.execute(FN_REQUIRE_STORY_APPROVAL)
    op.execute(
        "CREATE TRIGGER trg_stories_require_approval BEFORE INSERT OR UPDATE OF stage ON stories "
        "FOR EACH ROW EXECUTE FUNCTION saferoutezw_require_story_approval()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_stories_require_approval ON stories")
    op.execute("DROP FUNCTION IF EXISTS saferoutezw_require_story_approval()")
    # Dropping a table drops its triggers with it.
    op.drop_table("story_reviews")
    op.drop_table("story_scripts")
    op.drop_table("stories")

    # Reporters cannot exist under the old vocabulary; they become contributors (no access).
    op.execute("UPDATE users SET role = 'contributor' WHERE role = 'reporter'")
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
    op.create_check_constraint(op.f("ck_users_role_valid"), "users", f"role IN ({OLD_ROLES})")
