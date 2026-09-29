"""Create the missing `uq_stock_product_id_warehouse_id` unique index
(fix round 2, live prod-copy check).

The ORM model (`app/models/inventory.py::Stock.__table_args__`) has declared
`Index("uq_stock_product_id_warehouse_id", "product_id", "warehouse_id",
unique=True)` since before this lane started - `create_all` (every test's
blank schema, `scripts/bootstrap_env.py`) builds it, so every test exercising
`StockBalanceIngestService`'s insert-race handling sees the constraint and
gets a real `IntegrityError` on the losing INSERT. Production never got a
matching migration: checked against a prod copy
(`sorento_ai_automation_0924_full`) before writing this one - the only
unique keys `stock` actually carries there are `stock_pkey` and
`stock_product_id_warehouse_id_zone_id_key` (on `product_id, warehouse_id,
zone_id`). Every one of its 20,207 rows has `zone_id` NULL, and the PG
version predates `NULLS NOT DISTINCT`, so that key does not stop a duplicate
`(product_id, warehouse_id)` pair there either. Without this migration, a
genuine insert race in `StockBalanceIngestService` would silently create a
duplicate row on production instead of raising the `IntegrityError`
`_handle_insert_conflict` exists to catch.

**Refuses rather than dedupes on a conflict.** A stray duplicate found today
means two rows already disagree about one pair's quantity, and choosing
which to keep is a decision only whoever owns that inventory data should
make - `apply()` counts `(product_id, warehouse_id)` groups with more than
one row and raises `RuntimeError` naming the count and the query to find
them, never deleting or merging anything itself. Checked against the same
prod copy before writing this: 0 duplicate pairs among 20,207 rows.

`CREATE UNIQUE INDEX IF NOT EXISTS` - idempotent, and a no-op wherever the
model's own `create_all` already built it (every test schema, this lane's
own private CI database).

**Downgrade is a no-op.** The ORM model declares this index unconditionally
- a database that ran `downgrade()` would then disagree with what the model
itself expects (the same reasoning `sb1_stock_balances_grant.py`'s own
no-op downgrade documents, for a different index). Dropping a production
unique index is also not a decision this migration should make silently on
a rollback.

Revision ID: sb2_stock_pair_unique
Revises: sb1_stock_balances_grant
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op

revision = "sb2_stock_pair_unique"
down_revision = "sb1_stock_balances_grant"
branch_labels = None
depends_on = None

#: Named so both `apply()`'s error message and a human running it by hand
#: get the exact same query.
_DUPLICATE_PAIRS_QUERY = (
    "SELECT product_id, warehouse_id, count(*) AS n "
    "FROM stock "
    "GROUP BY product_id, warehouse_id "
    "HAVING count(*) > 1"
)


def apply(bind) -> None:
    """Refuses on any existing duplicate `(product_id, warehouse_id)` group,
    otherwise creates the index (idempotent)."""
    duplicate_count = bind.execute(
        sa.text(f"SELECT count(*) FROM ({_DUPLICATE_PAIRS_QUERY}) AS dupes")
    ).scalar()
    if duplicate_count:
        raise RuntimeError(
            f"{duplicate_count} (product_id, warehouse_id) pair(s) already have more "
            "than one stock row - refusing to create uq_stock_product_id_warehouse_id "
            "without a human choosing which row to keep for each. Find them with:\n"
            f"{_DUPLICATE_PAIRS_QUERY}"
        )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_product_id_warehouse_id "
            "ON stock (product_id, warehouse_id)"
        )
    )


def revert(bind) -> None:
    """No-op (fix round 2) - see the module docstring for why."""


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
