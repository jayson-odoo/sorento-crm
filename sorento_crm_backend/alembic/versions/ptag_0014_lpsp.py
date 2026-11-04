"""Price tag LP/SP per line, default tag template, combo tag templates (PRICETAG-LPSP).

documentation/plans/dealer-kit/PLAN-pricetag-lpsp-04nov.md, slice S1.

1. ``price_tag_request_lines.price_type`` VARCHAR(16) NULL, CHECK in ('list','selling'),
   backfilled from the request's ``price_mode`` so every existing line keeps what it printed.
2. ``dealer_kit.product_tag_template.is_default`` plus a partial unique index: one default
   link per product.
3. ``dealer_kit.combo_tag_template``: the combo's own tag templates, same shape as the product
   links (CASCADE on both FKs, unique (combo_id, template_id), one default per combo).

Idempotent (IF NOT EXISTS everywhere): a database built by ``create_all`` already holds all of
it. Downgrade drops everything added.

Revision ID: ptag_0014_lpsp
Revises: oiod_0001_backfill
Create Date: 2026-11-04
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "ptag_0014_lpsp"
down_revision = "oiod_0001_backfill"
branch_labels = None
depends_on = None


def _dk() -> str:
    """The dealer_kit schema prefix, read from where ``tag_template`` lives on this
    connection's search_path (see ``ptpt_0001_product_tag_templates._dk``)."""
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
        "ALTER TABLE price_tag_request_lines ADD COLUMN IF NOT EXISTS price_type VARCHAR(16) NULL"
    )
    # conrelid, not just conname: the name repeats in every schema holding the table.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_price_tag_request_lines_price_type'
                  AND conrelid = 'price_tag_request_lines'::regclass
            ) THEN
                ALTER TABLE price_tag_request_lines
                    ADD CONSTRAINT ck_price_tag_request_lines_price_type
                    CHECK (price_type IN ('list','selling'));
            END IF;
        END $$;
        """
    )
    op.execute(
        "UPDATE price_tag_request_lines l SET price_type = r.price_mode "
        "FROM price_tag_requests r "
        "WHERE r.id = l.request_id AND l.price_type IS NULL "
        "AND r.price_mode IN ('list','selling')"
    )

    op.execute(
        f"ALTER TABLE {dk}product_tag_template "
        "ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_product_tag_template_default "
        f"ON {dk}product_tag_template (product_id) WHERE is_default"
    )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {dk}combo_tag_template (
            id UUID PRIMARY KEY,
            combo_id UUID NOT NULL REFERENCES product_combos(id) ON DELETE CASCADE,
            template_id UUID NOT NULL REFERENCES {dk}tag_template(id) ON DELETE CASCADE,
            is_default BOOLEAN NOT NULL DEFAULT false,
            created_by VARCHAR NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            CONSTRAINT uq_dealer_kit_combo_tag_template UNIQUE (combo_id, template_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dealer_kit_combo_tag_template_template_id "
        f"ON {dk}combo_tag_template (template_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_dealer_kit_combo_tag_template_default "
        f"ON {dk}combo_tag_template (combo_id) WHERE is_default"
    )


def downgrade() -> None:
    dk = _dk()
    op.execute(f"DROP TABLE IF EXISTS {dk}combo_tag_template")
    op.execute(f"ALTER TABLE {dk}product_tag_template DROP COLUMN IF EXISTS is_default")
    op.execute("ALTER TABLE price_tag_request_lines DROP COLUMN IF EXISTS price_type")
