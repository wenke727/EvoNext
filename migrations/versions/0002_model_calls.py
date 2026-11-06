"""Bounded paid-call receipts; no changes to legacy or trajectory storage."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("model_call_receipts",
        sa.Column("call_key", sa.String(64), primary_key=True),
        sa.Column("budget_scope", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("status_code", sa.Integer),
        sa.Column("response_body", sa.Text),
        sa.Column("trace_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('sending','received','unknown')", name="model_call_status"),
        sa.CheckConstraint("status <> 'received' OR (status_code IS NOT NULL AND response_body IS NOT NULL)",
                           name="model_call_received_payload"), schema="evonext")
    op.create_index("ix_model_calls_budget_time", "model_call_receipts",
                    ["budget_scope", "created_at"], schema="evonext")


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; use an approved forward migration")
