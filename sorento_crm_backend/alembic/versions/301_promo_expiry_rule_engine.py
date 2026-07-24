"""Promotion-expiry rule engine + compiled-PDF batch columns.

Adds:
- ``automations.conditions_json`` (JSONB, nullable) — the rule-engine condition
  tree filtering which trigger matches an automation acts on.
- ``promotions.expiry_notified_at`` (timestamp, nullable) — when the promo was
  last emailed as expiring.
- ``promotions.expiry_notify_batch_id`` (uuid, nullable, indexed) — the batch a
  promo belongs to for the reminder-email deep link + list filter.

Idempotent (IF NOT EXISTS) so a partial prior apply re-runs cleanly.

Revision ID: 301_promo_expiry_rule_engine
Revises: 300_poly_source_entity_id_uuid
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "301_promo_expiry_rule_engine"
down_revision = "300_poly_source_entity_id_uuid"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE automations ADD COLUMN IF NOT EXISTS conditions_json JSONB"
    )
    op.execute(
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS expiry_notified_at "
        "TIMESTAMP WITHOUT TIME ZONE"
    )
    op.execute(
        "ALTER TABLE promotions ADD COLUMN IF NOT EXISTS expiry_notify_batch_id uuid"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_promotions_expiry_notify_batch_id "
        "ON promotions (expiry_notify_batch_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_promotions_expiry_notify_batch_id")
    op.execute("ALTER TABLE promotions DROP COLUMN IF EXISTS expiry_notify_batch_id")
    op.execute("ALTER TABLE promotions DROP COLUMN IF EXISTS expiry_notified_at")
    op.execute("ALTER TABLE automations DROP COLUMN IF EXISTS conditions_json")
