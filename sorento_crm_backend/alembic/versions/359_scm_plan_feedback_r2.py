"""scm plan feedback round 2: cover scope on the policy, debtor code on the sales order

Revision ID: 359_scm_plan_feedback_r2
Revises: 358_scm_po_spo_history_aliases
Create Date: 2026-08-15

Additive columns, ONE revision, shared byte-for-byte by the two branches that need them
(demand truth writes `sales_orders.debtor_code` and reads `sales_order_lines.unit_price`;
cover sourcing reads `scm.reorder_policy.cover_scope`). Identical files added on both sides
merge clean; two revisions off the same parent would leave a dual head.

- `scm.reorder_policy.cover_scope`: where "use stock" may draw from before buying.
  `own_pool` = only warehouses in the row's own pool (its site), `all_locations` = today's
  behaviour. Existing rows get `own_pool` deliberately (captain: "either I use stock from
  BRW, or buy"), not NULL.
- `sales_orders.debtor_code`: the AutoCount debtor code as printed on the order, kept even
  when it resolves to no customer, so an order nobody can attribute is still attributable.
- `sales_order_lines.unit_price`: exists on every database restored from production but no
  migration in the chain ever created it (the same gap 342 closed for `source_doc_no`), and
  the model maps it from this release on. Guarded add, so it is free where the column is
  already there and decisive on a database built from the migrations alone.
"""
from alembic import op
import sqlalchemy as sa


revision = "359_scm_plan_feedback_r2"
down_revision = "358_scm_po_spo_history_aliases"
branch_labels = None
depends_on = None


def _line_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("sales_order_lines")}


def upgrade() -> None:
    op.add_column(
        "reorder_policy",
        sa.Column("cover_scope", sa.String(16), nullable=True,
                  server_default=sa.text("'own_pool'")),
        schema="scm",
    )
    op.execute("UPDATE scm.reorder_policy SET cover_scope = 'own_pool' WHERE cover_scope IS NULL")

    op.add_column(
        "sales_orders",
        sa.Column("debtor_code", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_sales_orders_debtor_code", "sales_orders", ["debtor_code"],
    )

    if "unit_price" not in _line_columns():
        op.add_column(
            "sales_order_lines",
            sa.Column("unit_price", sa.Numeric(15, 2), nullable=True),
        )


def downgrade() -> None:
    # `unit_price` is left in place: on a production-restored database it predates this
    # revision, and dropping it would destroy data the revision did not create.
    op.drop_index("ix_sales_orders_debtor_code", table_name="sales_orders")
    op.drop_column("sales_orders", "debtor_code")
    op.drop_column("reorder_policy", "cover_scope", schema="scm")
