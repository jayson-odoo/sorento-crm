"""PS-SAMPLE-TRACKING: the Stage 1 date answer and the DO that delivered a sample request.

Additive, nullable columns on `projects.sample_requests`:

- `date_feasible` / `proposed_delivery_date` / `date_note` / `date_answered_at` /
  `date_answered_by`: the sample team's answer to "can we meet the requested date?", given on
  Start processing (PLAN-sample-tracking-02nov.md rule 2).
- `consignment_order_id`: the AutoCount consignment (CG, a `sales_orders` row with
  `doc_type = 'consignment'`) the sample team linked as the delivery (owner, 2 Nov: "The sample
  delivery document is the consignment"). `ON DELETE SET NULL`: the request outlives the row.

Idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through `create_all`, can
take it in any order.

Revision ID: sst_0001_sample_tracking
Revises: ppq_0001_proposal_quotation
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "sst_0001_sample_tracking"
down_revision = "ppq_0001_proposal_quotation"
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
        f"ALTER TABLE {_T} ADD COLUMN IF NOT EXISTS consignment_order_id UUID "
        "REFERENCES sales_orders(id) ON DELETE SET NULL"
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS ix_sample_requests_consignment_order "
        f"ON {_T} (consignment_order_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS projects.ix_sample_requests_consignment_order")
    for col in (
        "consignment_order_id",
        "date_answered_by",
        "date_answered_at",
        "date_note",
        "proposed_delivery_date",
        "date_feasible",
    ):
        op.execute(f"ALTER TABLE {_T} DROP COLUMN IF EXISTS {col}")
