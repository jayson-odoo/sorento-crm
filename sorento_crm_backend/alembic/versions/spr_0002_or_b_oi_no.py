"""Spare part request: the OI number at final approval, and a revision on the same record.

SPARE-PART-OR-B (UAC documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md,
U2.1, U2.2, U2.2b, U4.2). Additive only:

* `projects.order_inquiries.oi_no varchar(20)`: the OI- number an approved spare part request
  carries beside its own OR- number, unique per company where set.
* `projects.order_inquiries.revision_state varchar(16)`: a revision of an approved request,
  open while the header stays raised for purchasing.
* `projects.order_inquiry_rows.revised_qty numeric(15,4)`: the qty that revision proposes.

Then the backfill (`spare_part_request_service.backfill_oi_numbers`): every approved spare
part request without an oi_no takes one in raised_at order; a legacy request already numbered
in the OI- series keeps its own number. Idempotent.

Revision ID: spr_0002_or_b_oi_no
Revises: dbr_0001_retention_settings
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "spr_0002_or_b_oi_no"
down_revision = "dbr_0001_retention_settings"
branch_labels = None
depends_on = None

_INDEX = "uq_order_inquiries_company_oi_no"


def upgrade() -> None:
    op.add_column(
        "order_inquiries",
        sa.Column("oi_no", sa.String(20), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiries",
        sa.Column("revision_state", sa.String(16), nullable=True),
        schema="projects",
    )
    op.add_column(
        "order_inquiry_rows",
        sa.Column("revised_qty", sa.Numeric(15, 4), nullable=True),
        schema="projects",
    )
    op.create_index(
        _INDEX,
        "order_inquiries",
        ["company_id", "oi_no"],
        unique=True,
        schema="projects",
        postgresql_where=sa.text("oi_no IS NOT NULL"),
    )
    from app.services.spare_part_request_service import backfill_oi_numbers

    backfill_oi_numbers(op.get_bind())


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="order_inquiries", schema="projects")
    op.drop_column("order_inquiry_rows", "revised_qty", schema="projects")
    op.drop_column("order_inquiries", "revision_state", schema="projects")
    op.drop_column("order_inquiries", "oi_no", schema="projects")
