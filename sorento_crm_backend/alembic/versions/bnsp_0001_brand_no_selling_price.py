"""Brands whose promotions carry no selling price; clear Cabana's invented ones

Revision ID: bnsp_0001_brand_no_selling_price
Revises: qcp_0001_cover_page_fields
Create Date: 2026-11-02 00:00:00.000000

CABANA-NO-SELLING-PRICE (owner, 2 Nov 2026): Cabana has no selling price; the n8n
flyer reader invented one on every Cabana promotion line.

1. `brands.no_promo_selling_price` (default false), set true for brand code CABANA.
2. DATA CLEAR (destructive, reversible): for every promotion line whose product's brand
   carries the flag, the old `promo_selling_price`, `discount_amount`, `discount_percent`
   are copied into `promotion_products_selling_price_backup`, then cleared. The downgrade
   writes them back from that table. Runs on prod only after the owner's yes.

No embedding re-queue: `promotion_product` is outside the embedding keep set
(`app/services/embedding_settings.py` RECORD_KEEP_SET), so a queued row would be refused
and nothing serves those vectors; the chatbot reads prices through the promotion-products
API, which masks them for a flagged brand.
"""
import sqlalchemy as sa
from alembic import op

revision = "bnsp_0001_brand_no_selling_price"
down_revision = "qcp_0001_cover_page_fields"
branch_labels = None
depends_on = None

BACKUP = "promotion_products_selling_price_backup"


def upgrade() -> None:
    op.add_column(
        "brands",
        sa.Column("no_promo_selling_price", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE brands SET no_promo_selling_price = true WHERE upper(brand_code) = 'CABANA'")
    upgrade_data()


def upgrade_data() -> None:
    """Back up then clear flagged-brand lines. Idempotent: a second run backs up nothing
    new (the first backup is kept) and clears nothing (already null)."""
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {BACKUP} (
            id uuid PRIMARY KEY,
            promo_selling_price numeric(12, 2),
            discount_amount numeric(12, 2),
            discount_percent numeric(5, 2),
            backed_up_at timestamp NOT NULL DEFAULT now()
        )
        """
    )
    flagged_lines = """
        SELECT pp.id FROM promotion_products pp
        JOIN products p ON p.id = pp.product_id
        JOIN brands b ON b.id = p.brand_id
        WHERE b.no_promo_selling_price
          AND (pp.promo_selling_price IS NOT NULL
               OR pp.discount_amount IS NOT NULL
               OR pp.discount_percent IS NOT NULL)
    """
    op.execute(
        f"""
        INSERT INTO {BACKUP} (id, promo_selling_price, discount_amount, discount_percent)
        SELECT pp.id, pp.promo_selling_price, pp.discount_amount, pp.discount_percent
        FROM promotion_products pp WHERE pp.id IN ({flagged_lines})
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        f"""
        UPDATE promotion_products
        SET promo_selling_price = NULL, discount_amount = NULL, discount_percent = NULL,
            updated_at = now()
        WHERE id IN ({flagged_lines})
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF to_regclass('{BACKUP}') IS NOT NULL THEN
                UPDATE promotion_products pp
                SET promo_selling_price = bk.promo_selling_price,
                    discount_amount = bk.discount_amount,
                    discount_percent = bk.discount_percent
                FROM {BACKUP} bk WHERE bk.id = pp.id;
            END IF;
        END $$
        """
    )
    op.execute(f"DROP TABLE IF EXISTS {BACKUP}")
    op.drop_column("brands", "no_promo_selling_price")
