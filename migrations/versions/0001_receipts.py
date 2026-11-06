"""New operation receipts only; never touch legacy tables or collections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS evonext")
    op.create_table("operation_receipts",
        sa.Column("operation_id", sa.String(128), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()), schema="evonext")
    op.create_index("ix_evonext_operation_receipts_snapshot_id", "operation_receipts", ["snapshot_id"], schema="evonext")


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; restore a tested backup or use a forward migration")
