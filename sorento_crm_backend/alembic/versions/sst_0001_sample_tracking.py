"""PS-SAMPLE-TRACKING: the Stage 1 date answer and the DO that delivered a sample request.

Additive, nullable columns on `projects.sample_requests`:

- `date_feasible` / `proposed_delivery_date` / `date_note` / `date_answered_at` /
  `date_answered_by`: the sample team's answer to "can we meet the requested date?", given on
  Start processing (PLAN-sample-tracking-02nov.md rule 2).
- `delivery_order_id`: the AutoCount DO that delivered it (rule 4). `ON DELETE SET NULL`: the
  request outlives a deleted DO row.

Idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can
take it in any order.

Revision ID: sst_0001_sample_tracking
Revises: qcp_0001_cover_page_fields
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "sst_0001_sample_tracking"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None

_T = "projects.sample_requests"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS date_feasible BOOLEAN")
    op.execute(f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS proposed_delivery_date DATE")
    op.execute(f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS date_note VARCHAR(255)")
    op.execute(f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS date_answered_at TIMESTAMP")
    op.execute(
        f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS date_answered_by VARCHAR(100) "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS delivery_order_id UUID "
        "REFERENCES orders(id) ON DELETE SET NULL"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_sample_requests_delivery_order ON {_T} (delivery_order_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS projects.ix_sample_requests_delivery_order")
    for col in (
        "delivery_order_id",
        "date_answered_by",
        "date_answered_at",
        "date_note",
        "proposed_delivery_date",
        "date_feasible",
    ):
        op.execute(f"ALTER TABLE {_T} DROP COLUMN IF EXISTS {col}")
