"""brands.is_chatbot_default, seeded to Sorento

Revision ID: bcd_0001_brand_chatbot_default
Revises: 511_attribute_first_lookup_sets
Create Date: 2026-09-26

Owner brief W5 on PR #833 (hand test round 2): "i would prefer sorento to be recommended
with a heavier preference". One brand per company is the chatbot's default: when a
customer names no brand, a counted set answers that brand's products first and names the
other brands' counts. Edited on Master Data > Brands.

The body is plain idempotent SQL so it also runs as-is on the shared local database,
which converges through `create_all` (the column may already be there) rather than
`alembic upgrade`: ADD COLUMN IF NOT EXISTS, then every brand named Sorento becomes the
default of its company unless that company already has one. Re-running changes nothing.
Downgrade drops the column.
"""
from alembic import op


revision = "bcd_0001_brand_chatbot_default"
down_revision = "511_attribute_first_lookup_sets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE brands ADD COLUMN IF NOT EXISTS is_chatbot_default BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        """
        UPDATE brands AS b
        SET is_chatbot_default = true
        WHERE b.id IN (
              -- One Sorento row per company, the active and oldest one first.
              SELECT DISTINCT ON (company_id) id FROM brands
              WHERE lower(trim(brand_name)) = 'sorento'
              ORDER BY company_id, is_active DESC, created_at, id
          )
          AND NOT EXISTS (
              SELECT 1 FROM brands AS other
              WHERE other.is_chatbot_default
                AND other.company_id IS NOT DISTINCT FROM b.company_id
          )
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE brands DROP COLUMN IF EXISTS is_chatbot_default")
