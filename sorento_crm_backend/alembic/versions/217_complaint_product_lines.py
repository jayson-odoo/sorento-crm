"""Per-product complaint line items (code + quantity + derived type).

Adds complaint_product_lines as the source of truth for affected products and
their per-product quantities. The legacy complaints.product_code / product_type
/ quantity Text columns are RETAINED and kept denormalized (index-aligned CSV)
from the lines so existing consumers (n8n webhook payload, public view) keep
working without rework.

Backfill: split the existing product_code / product_type CSVs index-aligned
into lines. The old single `quantity` cannot be attributed per product, so
backfilled lines get quantity NULL (the complaint-level quantity column is left
untouched for history).

Revision ID: 217_complaint_product_lines
Revises: 216_portal_attachments_accept_text
Create Date: 2026-05-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "217_complaint_product_lines"
down_revision = "216_portal_attachments_accept_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "complaint_product_lines",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("complaint_id", sa.dialects.postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("product_code", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Text(), nullable=True),
        sa.Column("product_type", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_complaint_product_lines_complaint_id",
        "complaint_product_lines",
        ["complaint_id"],
    )

    # Backfill: explode product_code CSV into one line per code, pairing
    # product_type by the same index. quantity left NULL (cannot attribute the
    # old single value per product). gen_random_uuid() for ids.
    op.execute(
        sa.text(
            """
            INSERT INTO complaint_product_lines
                (id, complaint_id, product_code, quantity, product_type, sort_order)
            SELECT
                gen_random_uuid(),
                c.id,
                btrim(pc.code) AS product_code,
                NULL,
                btrim(NULLIF(split_part(coalesce(c.product_type, ''), ',', pc.ord::int), '')) AS product_type,
                pc.ord - 1 AS sort_order
            FROM complaints c
            CROSS JOIN LATERAL unnest(string_to_array(coalesce(c.product_code, ''), ','))
                WITH ORDINALITY AS pc(code, ord)
            WHERE btrim(pc.code) <> ''
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_complaint_product_lines_complaint_id", table_name="complaint_product_lines")
    op.drop_table("complaint_product_lines")
