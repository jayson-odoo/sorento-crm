"""seed the product_discontinued_check scheduled task (idempotent)

The cron row that drives the product-discontinued batch notification is runtime
data, not schema — so it never reached prod (the seed script is manual). This
data migration inserts it if absent, so every environment gets it automatically
on `alembic upgrade head` (run by start.sh on deploy). Safe to re-run: guarded by
NOT EXISTS on the unique key.

Revision ID: c1d2e3f4a5b6
Revises: b7c1d2e3f4a5
Create Date: 2026-06-22
"""
from alembic import op


revision = "c1d2e3f4a5b6"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO scheduled_tasks
            (id, key, name, description, enabled, interval_unit, interval_value,
             timezone, created_at, updated_at)
        SELECT gen_random_uuid(),
               'product_discontinued_check',
               'Product Discontinued Notification',
               'Reports newly-discontinued products (batched) to subscribed staff. '
               'Each run notifies once with the count + a deep link to the product '
               'list filtered to that batch.',
               true, 'minutes', 15, 'UTC', now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM scheduled_tasks WHERE key = 'product_discontinued_check'
        );
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM scheduled_tasks WHERE key = 'product_discontinued_check';"
    )
