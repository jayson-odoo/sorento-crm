"""product list-price change notification (PRODUCT-FIELD-CHANGE-NOTIFY)

Second watched product field of product_watched_field_notify_service:

* products.list_price_notified / list_price_notified_at / list_price_notify_batch_id:
  the watermark. Backfilled to the current list_price so day one reports nothing.
* users.notify_email_on_product_list_price / notify_whatsapp_on_product_list_price:
  per-user opt-in, same shape as the discontinued pair.
* scheduled_tasks row 'product_list_price_check' (15 minutes, like the discontinued one).

Idempotent (IF NOT EXISTS / NOT EXISTS) so a DB converged through create_all upgrades cleanly.

Revision ID: pfcn_0001_list_price_notify
Revises: sbt_0001_billing_subtotal_lines
Create Date: 2026-11-07
"""
from alembic import op


revision = "pfcn_0001_list_price_notify"
down_revision = "sbt_0001_billing_subtotal_lines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS list_price_notified NUMERIC(12, 2)")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS list_price_notified_at TIMESTAMP")
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS list_price_notify_batch_id UUID")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_products_list_price_notify_batch_id "
        "ON products (list_price_notify_batch_id)"
    )
    op.execute(
        "UPDATE products SET list_price_notified = list_price WHERE list_price_notified IS NULL"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_email_on_product_list_price "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_whatsapp_on_product_list_price "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        """
        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, created_at, updated_at)
        SELECT gen_random_uuid(),
               'product_list_price_check',
               'Product List Price Change Notification',
               'Reports products whose list price changed since the last run (batched '
               'per company) to subscribed staff, with old and new price per product.',
               true, 'minutes', 15, 'UTC', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'product_list_price_check'
        );
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_tasks WHERE key = 'product_list_price_check'")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS notify_whatsapp_on_product_list_price")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS notify_email_on_product_list_price")
    op.execute("DROP INDEX IF EXISTS ix_products_list_price_notify_batch_id")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS list_price_notify_batch_id")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS list_price_notified_at")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS list_price_notified")
