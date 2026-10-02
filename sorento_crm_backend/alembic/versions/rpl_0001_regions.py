"""Packing list regions: inbound_shipments.regions + attachments.regions (REGION-PACKING-LIST).

Additive. Existing shipments take the column default (West only) as the column is added.

Revision ID: rpl_0001_regions
Revises: grn_pull_0001_perm
"""
from alembic import op

revision = "rpl_0001_regions"
down_revision = "grn_pull_0001_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inbound_shipments ADD COLUMN IF NOT EXISTS regions text[] NOT NULL DEFAULT '{west}'")
    op.execute("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS regions text[] NULL")
    op.execute(
        "ALTER TABLE inbound_shipments ADD CONSTRAINT ck_inbound_shipments_regions "
        "CHECK (cardinality(regions) >= 1 AND regions <@ ARRAY['west','east']::text[])"
    )
    op.execute(
        "ALTER TABLE attachments ADD CONSTRAINT ck_attachments_regions "
        "CHECK (regions IS NULL OR (cardinality(regions) >= 1 AND regions <@ ARRAY['west','east']::text[]))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS ck_attachments_regions")
    op.execute("ALTER TABLE inbound_shipments DROP CONSTRAINT IF EXISTS ck_inbound_shipments_regions")
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS regions")
    op.execute("ALTER TABLE inbound_shipments DROP COLUMN IF EXISTS regions")
