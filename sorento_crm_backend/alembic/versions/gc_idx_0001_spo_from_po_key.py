"""Index the PO -> SPO key on both of its sides (GOODSCHAIN-INDEX-QUERY).

``documentation/plans/scm/PLAN-goodschain-index-query-27oct.md``. Prod incident 27 Oct 2026:
Stock Debt timed out. ``goods_chain.transferred_allocations`` matches allocations on
(from_po_number, btrim(from_po_line_ref), product_id, company_id) and no index covered it, so
every call read the whole table. The PO line side, read backwards by
``goods_chain._po_lines_feeding`` and Stock Debt's ``_follow_totals``, walked every line of
each PO named (crew profiling on the local clone: 1.2 s for ~949 keys, 28 ms with
``ix_purchase_order_lines_src_key``).

On prod (27 Oct): ``ix_spo_allocations_from_po_key`` was built by hand, same name and shape,
and is VALID, so it is kept as it is. ``ix_purchase_order_lines_src_key`` ships only through
this revision (owner: no more hand-run SQL on prod). Either way an INVALID index of that name
(the owner's first CONCURRENTLY build of the spo_allocations one was interrupted and left one,
which IF NOT EXISTS then kept) is dropped and rebuilt.

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

#: (table, index, columns): the two halves of the key.
INDEXES = (
    (
        "spo_allocations",
        "ix_spo_allocations_from_po_key",
        "(from_po_number, btrim(from_po_line_ref), product_id, company_id)",
    ),
    (
        "purchase_order_lines",
        "ix_purchase_order_lines_src_key",
        "(btrim(source_ref), product_id, company_id)",
    ),
)
INDEX_LOCK_TIMEOUT = "30s"


def _index_valid(bind, table: str, name: str):
    """pg_index.indisvalid for the index (True / False), or None when there is none."""
    return bind.execute(
        sa.text(
            # Through the table, not to_regclass(name): an unqualified index name resolves along
            # the search_path, so a same-named index in a later schema would answer for it.
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE i.indrelid = CAST(:table AS regclass) AND c.relname = :name"
        ),
        {"table": table, "name": name},
    ).scalar()


def _ensure_index(bind, table: str, name: str, columns: str, *, concurrently: bool) -> None:
    """Build the index unless a VALID one exists; drop an INVALID leftover of a failed
    CONCURRENTLY build first, which IF NOT EXISTS would otherwise keep forever."""
    if _index_valid(bind, table, name) is True:
        return
    c = "CONCURRENTLY" if concurrently else ""
    if _index_valid(bind, table, name) is False:
        bind.execute(sa.text(f"DROP INDEX {c} IF EXISTS {name}"))
    bind.execute(sa.text(f"CREATE INDEX {c} IF NOT EXISTS {name} ON {table} {columns}"))
    if _index_valid(bind, table, name) is not True:
        raise RuntimeError(f"gc_idx_0001_spo_from_po_key: index {name} is INVALID after the build; drop it and rerun.")


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the SPO and PO syncs keep
    # writing both tables while it builds.
    with op.get_context().autocommit_block():
        bind = op.get_bind()
        # Each build waits for every open transaction on its table. Bound that wait so a
        # release fails instead of hanging; the INVALID index a timeout leaves is dropped and
        # rebuilt by the next run. Session level, since SET LOCAL does nothing outside a
        # transaction; restored after.
        previous = bind.execute(sa.text("SELECT current_setting('lock_timeout')")).scalar()
        bind.execute(sa.text(f"SET lock_timeout = '{INDEX_LOCK_TIMEOUT}'"))
        try:
            for table, name, columns in INDEXES:
                _ensure_index(bind, table, name, columns, concurrently=True)
        finally:
            bind.execute(sa.text("SELECT set_config('lock_timeout', :v, false)"), {"v": previous})


def downgrade():
    with op.get_context().autocommit_block():
        for _table, name, _columns in INDEXES:
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
