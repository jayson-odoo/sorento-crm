"""Price tag templates per product (PRICETAG-TEMPLATE-PER-PRODUCT).

documentation/plans/dealer-kit/PLAN-pricetag-template-per-product-02nov.md.

Two additive pieces, nothing existing is touched:

1. ``dealer_kit.product_tag_template``: which tag templates a product may
   print with. CASCADE on both FKs, unique (product_id, template_id).
2. ``price_tag_request_lines.tag_template_id``: the template a line prints
   with, FK ``dealer_kit.tag_template`` ON DELETE SET NULL.

Idempotent (IF NOT EXISTS everywhere): a database built by ``create_all``
from the models (CI's bootstrap, the shared dev DB) already holds both, and
an upgrade there is a no-op. Downgrade drops both.

Revision ID: ptpt_0001_product_tag_tmpl
Revises: qcp_0001_cover_page_fields
Create Date: 2026-11-02
"""
from __future__ import annotations

from alembic import op

revision = "ptpt_0001_product_tag_tmpl"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dealer_kit.product_tag_template (
            id UUID PRIMARY KEY,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES dealer_kit.tag_template(id) ON DELETE CASCADE,
            created_by VARCHAR NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_dealer_kit_product_tag_template UNIQUE (product_id, template_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dealer_kit_product_tag_template_template_id "
        "ON dealer_kit.product_tag_template (template_id)"
    )
    op.execute(
        "ALTER TABLE price_tag_request_lines "
        "ADD COLUMN IF NOT EXISTS tag_template_id UUID NULL"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'price_tag_request_lines_tag_template_id_fkey'
            ) THEN
                ALTER TABLE price_tag_request_lines
                    ADD CONSTRAINT price_tag_request_lines_tag_template_id_fkey
                    FOREIGN KEY (tag_template_id)
                    REFERENCES dealer_kit.tag_template(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS tag_template_id"
    )
    op.execute("DROP TABLE IF EXISTS dealer_kit.product_tag_template")
