"""Stamp the historical discontinued-product backlog as already notified.

`product_discontinued_check` reports products where `discontinued_notified_at IS
NULL`. It has never actually reported any, because the scheduler handed its handler a
session with no company scope and the fail-closed filter turned every query into zero
rows - so nothing has ever been stamped, and the backlog is the entire history of
discontinued products.

The moment the scope fix ships, the first tick sends ONE notification naming every one
of them. That already happened by accident on the shared dev database while testing
the fix:

    {"pending": 2716, "subscribers": 2, "notified_users": 2}

Stamping the backlog here makes the first real run a no-op, so only products
discontinued AFTER this deploy notify - which is what the job is for.

`discontinued_notify_batch_id` is deliberately left NULL: these rows were never part of
a real notification batch, and pointing them at a fabricated one would make the
batch's own drill-down lie about what was sent.

Revision ID: 312_backfill_discontinued_notified_at
Revises: 311_split_pr_approve_permission
"""
from alembic import op
from sqlalchemy import text

revision = "312_backfill_discontinued_notified_at"
down_revision = "311_split_pr_approve_permission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text(
            """
            UPDATE products
            SET discontinued_notified_at = now()
            WHERE is_discontinued = true
              AND discontinued_notified_at IS NULL
            """
        )
    )
    print(f"[312] stamped {result.rowcount} discontinued products as already notified")


def downgrade() -> None:
    # Not reversible: the pre-existing NULLs are indistinguishable from rows this
    # stamped, and clearing them all would re-arm the burst this migration exists to
    # prevent. Deliberately a no-op.
    pass
