"""Index orders (customer_id, order_date DESC NULLS LAST, created_at DESC) (TOWN-PROJECT-CITY).

documentation/plans/dashboard/PLAN-town-project-city-11nov.md. The Town places a dealer by the postcode of
its last 20 delivery orders, newest first (`snapshot._states`, a LATERAL with LIMIT 20 per customer). With
only `ix_orders_customer_id` Postgres reads and sorts each customer's whole order history; on a cold prod
copy the first build hit the 5 s statement timeout there (crew pass, 12 Nov). This index serves the 20 rows
directly. Same build shape as sodv_0001_ol_from_doc_idx: CONCURRENTLY, bounded lock wait, an INVALID
leftover dropped and rebuilt.

Revision ID: town_0003_orders_cust_date
Revises: qdp_0001_duplicate_party
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "town_0003_orders_cust_date"
down_revision = "qdp_0001_duplicate_party"
branch_labels = None
depends_on = None

INDEX = "ix_orders_customer_order_date"
COLUMNS = "customer_id, order_date DESC NULLS LAST, created_at DESC"
INDEX_LOCK_TIMEOUT = "30s"


def _index_valid(bind):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'orders'::regclass AND c.relname = :name"
        ),
        {"name": INDEX},
    ).scalar()


def _ensure_index(bind, *, concurrently: bool) -> None:
    """Build the index unless a VALID one exists; drop an INVALID leftover of a failed CONCURRENTLY
    build first, which IF NOT EXISTS would otherwise keep forever."""
    if _index_valid(bind) is True:
        return
    c = "CONCURRENTLY" if concurrently else ""
    if _index_valid(bind) is False:
        bind.execute(sa.text(f"DROP INDEX {c} IF EXISTS {INDEX}"))
    bind.execute(sa.text(f"CREATE INDEX {c} IF NOT EXISTS {INDEX} ON orders ({COLUMNS})"))
    if _index_valid(bind) is not True:
        raise RuntimeError(f"town_0003: index {INDEX} is INVALID after the build; drop it and rerun.")


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            _ensure_index(bind, concurrently=True)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    with op.get_context().autocommit_block():
        op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}"))
