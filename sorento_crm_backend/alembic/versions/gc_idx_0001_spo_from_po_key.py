"""Index the PO -> SPO key on spo_allocations (GOODSCHAIN-INDEX-QUERY).

``documentation/plans/scm/PLAN-goodschain-index-query-27oct.md``. Prod incident 27 Oct 2026:
Stock Debt timed out. ``goods_chain.transferred_allocations`` matches allocations on
(from_po_number, btrim(from_po_line_ref), product_id, company_id) and no index covered it, so
every call read the whole table.

Same name and shape as the index the owner built by hand on prod that morning, so there the
build is a no-op (IF NOT EXISTS) and the hand-made one is kept.

Revision ID: gc_idx_0001_spo_from_po_key
Revises: eem_0001_span_pass
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "gc_idx_0001_spo_from_po_key"
down_revision = "eem_0001_span_pass"
branch_labels = None
depends_on = None

INDEX = "ix_spo_allocations_from_po_key"
INDEX_LOCK_TIMEOUT = "30s"


def _index_valid(bind):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            # Through the table, not to_regclass(name): an unqualified index name resolves along
            # the search_path, so a same-named index in a later schema would answer for it.
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = 'spo_allocations'::regclass AND c.relname = :name"
        ),
        {"name": INDEX},
    ).scalar()


def _ensure_index(bind, *, concurrently: bool) -> None:
    """Build the index unless a VALID one exists; drop an INVALID leftover of a failed
    CONCURRENTLY build first, which IF NOT EXISTS would otherwise keep forever. That is
    prod's case: the owner's first hand-made CONCURRENTLY build on 27 Oct was interrupted
    and left this index INVALID, and his IF NOT EXISTS retry then did nothing."""
    if _index_valid(bind) is True:
        return
    c = "CONCURRENTLY" if concurrently else ""
    if _index_valid(bind) is False:
        bind.execute(sa.text(f"DROP INDEX {c} IF EXISTS {INDEX}"))
    bind.execute(
        sa.text(
            f"CREATE INDEX {c} IF NOT EXISTS {INDEX} ON spo_allocations "
            "(from_po_number, btrim(from_po_line_ref), product_id, company_id)"
        )
    )
    if _index_valid(bind) is not True:
        raise RuntimeError(f"gc_idx_0001_spo_from_po_key: index {INDEX} is INVALID after the build; drop it and rerun.")


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the SPO sync keeps writing
    # spo_allocations while it builds.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        # The build waits for every open transaction on spo_allocations. Bound that wait so a
        # release fails instead of hanging; the INVALID index a timeout leaves is dropped and
        # rebuilt by the next run. Session level, since SET LOCAL does nothing outside a
        # transaction; restored after.
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            _ensure_index(bind, concurrently=True)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    with op.get_context().autocommit_block():
        op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}"))
