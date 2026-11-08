"""Frozen independent Outcome requests and selected records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("outcome_runs",
        sa.Column("run_id", sa.String(36), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("frozen", JSONB(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("record", JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()), schema="evonext")
    op.create_index("ix_evonext_outcome_runs_snapshot_id", "outcome_runs",
                    ["snapshot_id"], schema="evonext")


def downgrade():
    op.drop_table("outcome_runs", schema="evonext")
