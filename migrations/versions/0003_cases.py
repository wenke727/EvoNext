"""Single canonical Case + append-only operator decisions.

This is not a migration of old EvoLoop Case records. PR #2's documentation-only
local device queue must use the next unused migration revision, not 0003.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("case_heads",
        sa.Column("case_id", sa.String(36), primary_key=True),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("source_step_id", sa.String(256)),
        sa.Column("source_version", sa.Integer()),
        sa.Column("issue_kind", sa.String(40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_refs", JSONB(), nullable=False),
        sa.Column("analysis_refs", JSONB(), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("review_revision", sa.Integer(), nullable=False),
        sa.Column("review_status", sa.String(32), nullable=False),
        sa.CheckConstraint("position >= 0", name="case_position"),
        sa.CheckConstraint("review_revision >= 0", name="case_review_revision"),
        sa.CheckConstraint("review_status IN ('pending','operator_confirmed','rejected','needs_evidence')",
                           name="case_review_status"),
        schema="evonext")
    op.create_index("ix_evonext_case_heads_snapshot_id", "case_heads", ["snapshot_id"],
                    schema="evonext")
    op.create_table("case_reviews",
        sa.Column("case_id", sa.String(36),
                  sa.ForeignKey("evonext.case_heads.case_id"), primary_key=True),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("decision IN ('confirmed','rejected','needs_evidence')",
                           name="case_decision"),
        schema="evonext")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use an approved forward migration")
