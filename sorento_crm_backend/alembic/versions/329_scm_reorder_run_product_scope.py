"""SCM: let a manual reorder run be narrowed to specific products.

`RunPlanningModal` grew a `product_codes[]` picker beside the warehouse picker and the
frontend sends it, but the request schema had no such field, so pydantic dropped it and a
planner who asked for one sku silently got all 3,123. Nothing on the results screen said the
scope had been ignored, which is the worst shape for a filter: it looks like it worked.

The scope has to be PERSISTED rather than passed through, because the evaluation runs later
in an RQ worker that receives only a run id. It sits beside `warehouse_ids`, the scope column
that already exists, in the same jsonb shape and for the same reason.

NULL and `[]` mean different things and both are load-bearing: NULL is "no product scope was
asked for" (the daily scheduled run, which must plan everything), while `[]` is "a scope was
asked for and nothing resolved" (a mistyped code, which must plan nothing rather than widen
to the whole catalogue and look deliberate).

Revision ID: 329_scm_reorder_run_product_scope
Revises: 328_scm_shipment_line_currency
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "329_scm_reorder_run_product_scope"
down_revision = "328_scm_shipment_line_currency"
branch_labels = None
depends_on = None


def _has_column(bind, table: str, column: str, schema: str = "public") -> bool:
    return column in {
        c["name"] for c in sa.inspect(bind).get_columns(table, schema=schema)
    }


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "reorder_run", "product_ids", schema="scm"):
        op.add_column(
            "reorder_run",
            sa.Column("product_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            schema="scm",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "reorder_run", "product_ids", schema="scm"):
        op.drop_column("reorder_run", "product_ids", schema="scm")
