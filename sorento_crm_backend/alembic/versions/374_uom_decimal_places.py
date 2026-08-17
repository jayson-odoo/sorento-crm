"""Canonical UOM divisibility: `units_of_measure.decimal_places` (front planning 6.4).

How finely a unit may be counted, `0..4`. `EA` is 0 and refuses `2.5`; `kg` at 3 accepts
it. The SCM product plan freezes this per run (`order_summary_row.uom_decimal_places`) so
a later edit here cannot move a run that is already calculated.

Three steps, in this order, because the backfill can only see NULL as "not classified
yet":

1. add the column NULLABLE;
2. backfill it from `app.services.uom_decimal_places.backfill_uom_decimal_places`, the
   same function the service layer uses - classification reads the unit NAME only (never
   the code, so `EA` named `Kilogram` is a measure unit), a measure name takes the
   greatest fractional scale actually observed in `order_lines.quantity`,
   `sales_order_lines.qty_ordered` / `qty_delivered` / `qty_required` and
   `purchase_order_lines.qty_ordered` / `qty_received` after trailing zeroes are dropped,
   capped at 4, and every count or unrecognised name takes 0. **No quantity row is
   rewritten**;
3. make it NOT NULL with server default 0 and the `0..4` CHECK.

**Behaviour on a row the backfill cannot value** - an unknown name, or a measure unit with
no transactions to measure - **is 0**, and that is also what step 3's default gives any row
inserted afterwards. So the rollout fallback survives: nothing is left NULL, nothing is
guessed, and a unit that genuinely needs decimals is corrected by an admin edit (or by
re-running the backfill, which re-values a row still sitting on the 0 fallback and leaves a
carried value alone).

Empty database is a supported case: the backfill selects no rows and writes nothing, so a
fresh `alembic upgrade head` passes through it untouched.

Revision ID: 374_uom_decimal_places
Revises: 373_merge_scm_stage0_1a
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa


revision = "374_uom_decimal_places"
down_revision = "373_merge_scm_stage0_1a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "units_of_measure",
        sa.Column("decimal_places", sa.SmallInteger(), nullable=True),
    )

    from app.services.uom_decimal_places import backfill_uom_decimal_places

    backfill_uom_decimal_places(op.get_bind())

    op.execute(
        "UPDATE units_of_measure SET decimal_places = 0 WHERE decimal_places IS NULL"
    )
    op.alter_column(
        "units_of_measure",
        "decimal_places",
        existing_type=sa.SmallInteger(),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.create_check_constraint(
        "ck_units_of_measure_decimal_places",
        "units_of_measure",
        "decimal_places >= 0 AND decimal_places <= 4",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_units_of_measure_decimal_places", "units_of_measure", type_="check"
    )
    op.drop_column("units_of_measure", "decimal_places")
