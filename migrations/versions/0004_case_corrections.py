"""A0-A3: task scope, shared Case correction draft, immutable frozen reviews.

The earlier 0003 migration belongs to PR #3; do not edit its historical content.
Local device queue (PR #2) must use the next unused Alembic revision on merge.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("case_heads",
                  sa.Column("scope", sa.String(12), nullable=False,
                            server_default="step"), schema="evonext")
    op.alter_column("case_heads", "position", nullable=True,
                    existing_type=sa.Integer(), schema="evonext")
    op.create_check_constraint("case_scope", "case_heads",
        "((scope='step' AND position IS NOT NULL AND position>=0) OR "
        "(scope='task' AND position IS NULL AND source_step_id IS NULL))", schema="evonext")

    op.add_column("case_reviews", sa.Column("draft_revision", sa.Integer()),
                  schema="evonext")
    op.add_column("case_reviews", sa.Column("draft_hash", sa.String(64)),
                  schema="evonext")
    op.add_column("case_reviews", sa.Column("frozen_draft", JSONB()),
                  schema="evonext")
    op.add_column("case_reviews", sa.Column("review_input_hash", sa.String(64)),
                  schema="evonext")

    op.create_table("case_drafts",
        sa.Column("case_id", sa.String(36),
                  sa.ForeignKey("evonext.case_heads.case_id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("draft_hash", sa.String(64), nullable=False),
        sa.Column("body", JSONB(), nullable=False),
        sa.Column("updated_by", sa.String(128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 1", name="case_draft_revision"),
        schema="evonext")
    op.create_table("case_commands",
        sa.Column("case_id", sa.String(36),
                  sa.ForeignKey("evonext.case_heads.case_id"), primary_key=True),
        sa.Column("command_id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("receipt", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()), schema="evonext")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use an approved forward migration")
