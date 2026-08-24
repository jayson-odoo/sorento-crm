"""transporters.updated_at - model declared it, migration 200 never created it.

Revision ID: 256_transporters_updated_at
Revises: 255_attachment_thumbnail_path
Create Date: 2026-07-02

The Transporter model (app/models/order.py) has an `updated_at` column, but the
create_table in 200_transporters_table only added `created_at`. Any query that
SELECTs the full model (e.g. entity_resolver looking up a transporter by
normalized_name during an order/DO update) fails on prod with
`column transporters.updated_at does not exist`. Add the missing column;
use idempotent IF NOT EXISTS so it is safe on any env that already has it.
"""
from alembic import op


revision = "256_transporters_updated_at"
down_revision = "255_attachment_thumbnail_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE transporters ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE transporters DROP COLUMN IF EXISTS updated_at")
