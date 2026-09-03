"""scm: shipment_line_spo_link is no longer one row per shipment line, ever.

R1, `PLAN-scm-spo-planner-feedback-3sep.md` ("many SPOs per container"): a shipment line
that Create SPO left a remainder on must be convertible again by a later run, and each run
that matches the line writes its own row rather than replacing the one before it. Migration
406's `uq_scm_shipment_spo_link_line` UNIQUE index made a second matched row for the same
line an integrity error; this drops it and replaces it with a plain index (every reader
still filters/aggregates by `inbound_shipment_line_id`, it simply no longer has to be one
row).

Revision ID: 469_shipment_spo_link_not_unique
Revises: 468_merge_overdue_grace_desc
Create Date: 2026-09-04
"""
from alembic import op

revision = "469_shipment_spo_link_not_unique"
down_revision = "468_merge_overdue_grace_desc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_scm_shipment_spo_link_line", table_name="shipment_line_spo_link", schema="scm"
    )
    op.create_index(
        "ix_scm_shipment_spo_link_line", "shipment_line_spo_link",
        ["inbound_shipment_line_id"], schema="scm",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scm_shipment_spo_link_line", table_name="shipment_line_spo_link", schema="scm"
    )
    op.create_index(
        "uq_scm_shipment_spo_link_line", "shipment_line_spo_link",
        ["inbound_shipment_line_id"], unique=True, schema="scm",
    )
