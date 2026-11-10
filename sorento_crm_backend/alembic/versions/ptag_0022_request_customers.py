"""Price tag request: several customers on one request.

PRICETAG-REQUEST-LAYOUT (plan documentation/plans/dealer-kit/PLAN-pricetag-request-layout-10nov.md):
`price_tag_requests.customers JSONB NULL`, a list of `{code, name}`. The first is mirrored into
`debtor_code` / `debtor_name` by the model. Idempotent (`IF NOT EXISTS`), additive only.

Revision ID: ptag_0022_request_customers
Revises: town_0001_view_perm
"""
from __future__ import annotations

from alembic import op

revision = "ptag_0022_request_customers"
down_revision = "town_0001_view_perm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE price_tag_requests ADD COLUMN IF NOT EXISTS customers JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE price_tag_requests DROP COLUMN IF EXISTS customers")
