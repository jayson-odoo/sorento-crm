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
Revises: pss_0001_spec_sheet
Create Date: 2026-11-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "ptpt_0001_product_tag_tmpl"
down_revision = "pss_0001_spec_sheet"
branch_labels = None
depends_on = None


def _dk() -> str:
    """The dealer_kit schema prefix, read from where ``tag_template`` actually
    lives on this connection's search_path: ``dealer_kit.`` in production, the
    scratch ``..._dealer_kit`` sibling under test. Same reason as
    ``ptag_0013_r10._dealer_kit_schema``: a literal ``dealer_kit.`` under test
    hits the real schema, and an UNQUALIFIED ``CREATE TABLE IF NOT EXISTS``
    would create in the first search_path schema instead (measured)."""
    schema = op.get_bind().execute(
        sa.text(
            "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.oid = to_regclass('tag_template')"
        )
    ).scalar()
    return f'"{schema or "dealer_kit"}".'


def upgrade() -> None:
    dk = _dk()
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {dk}product_tag_template (
            id UUID PRIMARY KEY,
            product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES {dk}tag_template(id) ON DELETE CASCADE,
            created_by VARCHAR NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_dealer_kit_product_tag_template UNIQUE (product_id, template_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dealer_kit_product_tag_template_template_id "
        f"ON {dk}product_tag_template (template_id)"
    )
    op.execute(
        "ALTER TABLE price_tag_request_lines "
        "ADD COLUMN IF NOT EXISTS tag_template_id UUID NULL"
    )
    # conrelid, not just conname: the constraint name repeats in every schema
    # that holds a price_tag_request_lines table.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'price_tag_request_lines_tag_template_id_fkey'
                  AND conrelid = 'price_tag_request_lines'::regclass
            ) THEN
                ALTER TABLE price_tag_request_lines
                    ADD CONSTRAINT price_tag_request_lines_tag_template_id_fkey
                    FOREIGN KEY (tag_template_id)
                    REFERENCES {dk}tag_template(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    dk = _dk()
    op.execute(
        "ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS tag_template_id"
    )
    op.execute(f"DROP TABLE IF EXISTS {dk}product_tag_template")
