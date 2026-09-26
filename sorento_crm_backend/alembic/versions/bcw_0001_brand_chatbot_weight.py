"""brands.chatbot_weight replaces brands.is_chatbot_default

Revision ID: bcw_0001_brand_chatbot_weight
Revises: bcd_0001_brand_chatbot_default
Create Date: 2026-09-27

Owner console test of round 3 on PR #833 (27 Sep 2026, R1): "i want weights as brand
preference instead of switch". Every brand carries a chatbot weight (0 = no preference).
When a customer names no brand, a counted set answers the highest weighted brand the set
reaches and names the other brands in weight order. Edited on Master Data > Brands.

Seed: a brand that was its company's default carries 1.5 (the owner's own example value);
a company with no weighted brand yet gets 1.5 on one Sorento row. Every other brand is 0.
Then the switch column is dropped.

The body is plain idempotent SQL so it also runs as-is on the shared local database, which
converges through `create_all` (the weight may already be there and already tuned, the
switch may already be gone). Re-running changes nothing. Downgrade puts the switch back on
each company's top weighted brand and drops the weight.
"""
import sqlalchemy as sa
from alembic import op


revision = "bcw_0001_brand_chatbot_weight"
down_revision = "bcd_0001_brand_chatbot_default"
branch_labels = None
depends_on = None

SEED_WEIGHT = 1.5


def _has_column(name: str) -> bool:
    return name in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("brands")}


def upgrade() -> None:
    op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS chatbot_weight NUMERIC(6,2) NOT NULL DEFAULT 0")
    if _has_column("is_chatbot_default"):
        # The round 2 choice is kept: a company's default becomes its top weight, unless
        # staff already weighted a brand there.
        op.execute(
            f"""
            UPDATE brands AS b SET chatbot_weight = {SEED_WEIGHT}
            WHERE b.is_chatbot_default
              AND NOT EXISTS (
                  SELECT 1 FROM brands AS other
                  WHERE other.chatbot_weight > 0
                    AND other.company_id IS NOT DISTINCT FROM b.company_id
              )
            """
        )
    op.execute(
        f"""
        UPDATE brands AS b SET chatbot_weight = {SEED_WEIGHT}
        WHERE b.id IN (
              -- One Sorento row per company, the active and oldest one first.
              SELECT DISTINCT ON (company_id) id FROM brands
              WHERE lower(trim(brand_name)) = 'sorento'
              ORDER BY company_id, is_active DESC, created_at, id
          )
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
            ORDER BY company_id, chatbot_weight DESC, is_active DESC, created_at, id
        )
        """
    )
    op.execute("ALTER TABLE brands DROP COLUMN IF EXISTS chatbot_weight")
