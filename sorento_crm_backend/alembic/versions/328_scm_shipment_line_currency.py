"""SCM S3b: a currency for the incoming cost on inbound_shipment_lines.

``inbound_shipment_lines.unit_cost`` already exists. What it never had is a unit: the
table has no currency column, so a captured incoming cost of 12.50 carries no statement
of what 12.50 is, and cannot be compared with ``purchase_order_lines.unit_cost`` at all
(AC-C3.2, AC-C3.4).

``String(3)`` mirrors ``purchase_order_lines.currency`` exactly, because the point of the
column is that the two figures line up.

NULLABLE, with no server default and no backfill. Where no currency is knowable it stays
NULL, and that is the correct value rather than a gap to be filled later: the currency is
resolved at capture time from the linked PO line, and a house default written here would
silently assert that ordered and incoming are in the same unit, which is precisely what
the variance means. All 1,015 existing rows are uncosted (``unit_cost`` is populated in 0
of them), so there is no cost in need of a unit to backfill.

``scripts/bootstrap_env`` needs no change for this revision: the column comes from the ORM
model, which ``create_all`` emits, and there is no data step.

Revision ID: 328_scm_shipment_line_currency
Revises: 327_scm_coverage_config
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "328_scm_shipment_line_currency"
down_revision = "327_scm_coverage_config"
branch_labels = None
depends_on = None

_TABLE = "inbound_shipment_lines"
_COLUMN = "currency"


def _has_column(bind, table: str, column: str, schema: str = "public") -> bool:
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
            ),
            {"s": schema, "t": table, "c": column},
        ).scalar()
    )


def upgrade() -> None:
    # Guarded because a database built by scripts/bootstrap_env gets the column from
    # create_all and is then stamped at head; re-running the chain there must not fail.
    bind = op.get_bind()
    if not _has_column(bind, _TABLE, _COLUMN):
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=3), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, _TABLE, _COLUMN):
        op.drop_column(_TABLE, _COLUMN)
