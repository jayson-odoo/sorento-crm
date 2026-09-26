"""brands.chatbot_weight replaces brands.is_chatbot_default, Sorento seeded highest

Revision ID: bcw_0001_brand_chatbot_weight
Revises: bcd_0001_brand_chatbot_default
Create Date: 2026-09-27

Owner console test of round 3 on PR #833, ruling R1 (27 Sep 2026): "i want weights as
brand preference instead of switch". Every brand carries a chatbot weight. When a
customer names no brand, a counted set answers the highest weighted brand it reaches and
names the other brands in weight order. Edited on Master Data > Brands.

Seed: a brand that was its company's default (bcd_0001) carries 1.5, the owner's own
example value ("sorento to be 1.5, cabana to be 0.5, mocha to be 0.1") and the brand
preference `product_spec_registry.value_weights` already holds. A company with no
weighted brand then gets 1.5 on its Sorento rows. Every other brand stays 0. A company
whose staff already weighted a brand is left alone.

Plain idempotent SQL, so the body also runs on the shared local database, which converges
through `create_all` (the weight may already be there, the switch may already be gone).
Downgrade puts the switch back on each company's top weighted brand.
"""
from alembic import op


revision = "bcw_0001_brand_chatbot_weight"
down_revision = "bcd_0001_brand_chatbot_default"
branch_labels = None
depends_on = None

_HAS_SWITCH = """
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = 'brands' AND column_name = 'is_chatbot_default'
"""


def upgrade() -> None:
    op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS chatbot_weight NUMERIC(6,2) NOT NULL DEFAULT 0")
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS ({_HAS_SWITCH}) THEN
                UPDATE brands AS b SET chatbot_weight = 1.5
                WHERE b.is_chatbot_default
                  AND NOT EXISTS (
                      SELECT 1 FROM brands AS other
                      WHERE other.chatbot_weight > 0
                        AND other.company_id IS NOT DISTINCT FROM b.company_id
                  );
            END IF;
        END $$
        """
    )
    op.execute(
        """
        UPDATE brands AS b SET chatbot_weight = 1.5
        WHERE lower(trim(b.brand_name)) = 'sorento'
          AND NOT EXISTS (
              SELECT 1 FROM brands AS other
              WHERE other.chatbot_weight > 0
                AND other.company_id IS NOT DISTINCT FROM b.company_id
          )
        """
    )
    op.execute("ALTER TABLE brands DROP COLUMN IF EXISTS is_chatbot_default")


def downgrade() -> None:
    op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS is_chatbot_default BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        """
        UPDATE brands SET is_chatbot_default = true
        WHERE id IN (
            SELECT DISTINCT ON (company_id) id FROM brands
            WHERE chatbot_weight > 0
            ORDER BY company_id, chatbot_weight DESC, created_at, id
        )
        """
    )
    op.execute("ALTER TABLE brands DROP COLUMN IF EXISTS chatbot_weight")
