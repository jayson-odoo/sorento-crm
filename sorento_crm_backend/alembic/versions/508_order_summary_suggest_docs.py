"""`scm.order_summary_row` gains `suggestion` (Slice 2) and `po_open_docs` /
`incoming_spo_docs` (Slice 3), issue #794/#795,
`PLAN-product-grain-project-buy-no-level.md`.

All three additive and nullable, no backfill. `suggestion` is populated by this slice's
`write_rows` change; `po_open_docs` / `incoming_spo_docs` land now so Slice 3 (the PO/SPO
document breakdown under the two supply cells) needs no second migration, but their
population is Slice 3's own change - both stay NULL until then.

Revision ID: 508_order_summary_suggest_docs
Revises: 507_pi_link_packing_row
"""
import sqlalchemy as sa
from alembic import op

revision = "508_order_summary_suggest_docs"
down_revision = "507_pi_link_packing_row"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("suggestion", "TEXT"),
    ("po_open_docs", "JSONB"),
    ("incoming_spo_docs", "JSONB"),
)


def apply(bind) -> None:
    for name, sql_type in _COLUMNS:
        bind.execute(
            sa.text(
                f"ALTER TABLE scm.order_summary_row ADD COLUMN IF NOT EXISTS "
                f"{name} {sql_type}"
            )
        )


def revert(bind) -> None:
    for name, _sql_type in reversed(_COLUMNS):
        bind.execute(
            sa.text(f"ALTER TABLE scm.order_summary_row DROP COLUMN IF EXISTS {name}")
        )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
