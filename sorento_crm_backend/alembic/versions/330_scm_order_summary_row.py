"""SCM: freeze the Summary Order Report per run, and hold the order-quantity decision.

AC-C2.9 says a past week's report is reproducible: what Mr Loo saw when he decided has to be
recoverable, or the decision cannot be reviewed. A recomputation against today's order book
is explicitly not that - the book moves every day, so the shortfall he acted on would be gone
by the time anyone asked why. So the row is FROZEN by the run that produced it.

The grain is (run_id, product_id), not (run_id, product_id, warehouse_id), and that is the
whole reason this table exists rather than reusing `scm.recommendation_override`:

  * AC-C2.1 states the report is one row per product, NETWORK wide. A purchase order is
    raised once for the company, so the quantity a person decides is one figure per product.
  * M8-D5 decided the opposite grain for recommendations: `buy_scope` defaults to `warehouse`
    so each buy is tied to a real location rather than an aggregated network row. A run
    therefore holds SEVERAL recommendations per product, and `recommendation_override` hangs
    off one of them.

Both decisions stand. What follows is that the product-level decision has nowhere to live on
the per-warehouse recommendation, and splitting one chosen quantity across locations is the
allocator's job (it already produces the per-warehouse breakdown), not a person's. Writing the
decision against an arbitrary one of N recommendations would be the alternative, and it makes
the figure S4's worklist reads depend on row order.

Nullability carries meaning throughout and is not incidental:

  * `avg_daily_demand` is absent for roughly 38% of the book and `unit_volume_cbm` for 84%
    (no recorded dimensions). A zero would read as "already out of stock" and "no space
    needed", both decisions taken on a figure nobody measured. NULL so the screen can name
    the missing input instead.
  * `max_days_outstanding` is NULL when nothing is outstanding, which is different from 0
    days outstanding.
  * The four decision columns are NULL together until somebody decides. `suggested_qty` sits
    beside `chosen_qty` and is never replaced by it (AC-C2.8).

Revision ID: 330_scm_order_summary_row
Revises: 329_scm_reorder_run_product_scope
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "330_scm_order_summary_row"
down_revision = "329_scm_reorder_run_product_scope"
branch_labels = None
depends_on = None


def _has_table(bind, table: str, schema: str = "scm") -> bool:
    return sa.inspect(bind).has_table(table, schema=schema)


def upgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "order_summary_row"):
        return
    op.create_table(
        "order_summary_row",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("scm.reorder_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # -- the frozen network position (AC-C2.1, AC-C2.2) --------------------
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("on_hand", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("project_demand", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("dealer_outstanding", sa.Numeric(), nullable=False, server_default="0"),
        # Separate columns on purpose: their SUM drives the balance, the SPLIT is what a
        # person reads, because only the on-order half is still negotiable.
        sa.Column("qty_on_order", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("qty_in_transit", sa.Numeric(), nullable=False, server_default="0"),
        # The DATED shortfall (peak deficit over the timeline), not on hand + on order -
        # demand. A positive net position is still short when the supply that lifts it is
        # dated after the demand it is read as covering.
        sa.Column("shortfall", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("shortfall_at", sa.Date(), nullable=True),
        sa.Column("suggested_qty", sa.Numeric(), nullable=False, server_default="0"),
        # -- inputs the consequence panel needs, nullable where absent --------
        sa.Column("avg_daily_demand", sa.Numeric(), nullable=True),
        sa.Column("unit_volume_cbm", sa.Numeric(), nullable=True),
        sa.Column(
            "spare_lands_at_warehouse_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("warehouses.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # -- what each aggregate opens to, so an icon can carry a count -------
        sa.Column(
            "project_demand_line_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "dealer_outstanding_line_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("max_days_outstanding", sa.Integer(), nullable=True),
        # -- the decision (AC-C2.7, AC-C2.8) ----------------------------------
        sa.Column("chosen_qty", sa.Numeric(), nullable=True),
        sa.Column(
            "chosen_supplier_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("suppliers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("source_system", sa.String(), nullable=True),
        sa.Column("source_ref", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="scm",
    )
    # One row per product per run. Without this a re-run of the writer duplicates the book
    # and the report reads whichever row comes back first, which is the `system_settings`
    # failure again: a screen that non-deterministically shows one of two figures.
    op.create_index(
        "uq_scm_order_summary_row_run_product",
        "order_summary_row",
        ["run_id", "product_id"],
        unique=True,
        schema="scm",
    )
    # The report is always read by run, and the decision worklist reads it by run too.
    op.create_index(
        "ix_scm_order_summary_row_run_id",
        "order_summary_row",
        ["run_id"],
        schema="scm",
    )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "order_summary_row"):
        return
    op.drop_index(
        "ix_scm_order_summary_row_run_id", table_name="order_summary_row", schema="scm"
    )
    op.drop_index(
        "uq_scm_order_summary_row_run_product",
        table_name="order_summary_row",
        schema="scm",
    )
    op.drop_table("order_summary_row", schema="scm")
