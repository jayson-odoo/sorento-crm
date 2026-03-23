"""Rename expected_arrival_date to estimated_arrival_date; drop eta (merged into one column).

Revision ID: 113_inbound_shipment_estimated_arrival
Revises: 112_drop_promotion_group_legacy_foc_columns
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "113_inbound_shipment_estimated_arrival"
down_revision = "112_drop_promotion_group_legacy_foc_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "inbound_shipments" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("inbound_shipments")}
    has_eta = "eta" in cols
    has_expected = "expected_arrival_date" in cols
    has_estimated = "estimated_arrival_date" in cols

    # Already migrated (e.g. partial apply): only drop legacy eta if present.
    if has_estimated and not has_expected:
        if has_eta:
            op.drop_column("inbound_shipments", "eta")
        return

    if has_expected and not has_estimated:
        if has_eta:
            op.execute(
                """
                UPDATE inbound_shipments
                SET expected_arrival_date = eta
                WHERE expected_arrival_date IS NULL AND eta IS NOT NULL
                """
            )
        op.execute(
            'ALTER TABLE inbound_shipments RENAME COLUMN expected_arrival_date TO estimated_arrival_date'
        )
        cols = {c["name"] for c in sa.inspect(bind).get_columns("inbound_shipments")}
        has_eta = "eta" in cols

    if has_eta:
        op.drop_column("inbound_shipments", "eta")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "inbound_shipments" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("inbound_shipments")}
    if "eta" not in cols:
        op.add_column("inbound_shipments", sa.Column("eta", sa.Date(), nullable=True))

    if "estimated_arrival_date" in cols and "expected_arrival_date" not in cols:
        op.execute(
            'ALTER TABLE inbound_shipments RENAME COLUMN estimated_arrival_date TO expected_arrival_date'
        )
