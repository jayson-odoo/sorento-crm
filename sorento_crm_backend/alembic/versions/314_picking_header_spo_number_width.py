"""Widen picking_headers.spo_number so a multi-SPO GRN can say which SPOs it covers.

AutoCount exports every SPO a GRN was received against into the ONE "Transfer
from" cell:

    SPO-2026/06-0020, SPO-2026/06-0021, SPO-2026/06-0022, SPO-2026/06-0023

71 characters into varchar(50), which aborted the whole import
(StringDataRightTruncation).

The column stays a DISPLAY field for that case: matching is scalar and stays
scalar (`_spo_match_key`, `_normalize_spo_number`, the packing-list
grouping all compare one normalized SPO), so a joined value equals no single SPO
and can never false-link. What widening buys is the operator seeing "covers these
four SPOs" in the GRN list instead of a bare dash. The per-line SPO remains the
value used for allocation matching.

255 rather than TEXT: it is still a bounded document reference, and a value beyond
this is bad source data the importer should reject with a stated reason rather
than store.

Revision ID: 314_picking_header_spo_number_width
Revises: 313_purchase_request_pic
"""
import sqlalchemy as sa
from alembic import op

revision = "314_picking_header_spo_number_width"
down_revision = "313_purchase_request_pic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "picking_headers",
        "spo_number",
        existing_type=sa.String(length=50),
        type_=sa.String(length=255),
        existing_nullable=True,
    )


def downgrade() -> None:
    # Truncate first: a value longer than 50 blocks the narrowing ALTER, and the
    # rows that motivated the widening are exactly the long ones.
    op.execute(
        "UPDATE picking_headers SET spo_number = left(spo_number, 50) "
        "WHERE spo_number IS NOT NULL AND length(spo_number) > 50"
    )
    op.alter_column(
        "picking_headers",
        "spo_number",
        existing_type=sa.String(length=255),
        type_=sa.String(length=50),
        existing_nullable=True,
    )
