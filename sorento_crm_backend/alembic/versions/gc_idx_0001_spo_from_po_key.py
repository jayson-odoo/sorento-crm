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

Never stalls a deploy or live work (owner, 27 Oct): the build is CONCURRENTLY under the repo's
migration limits (lock_timeout 5s, statement_timeout 180s, `app/utils/migration_timeouts.py`),
and a build that times out or fails logs a WARNING and lets this revision SUCCEED with the
index missing. The retry is `scripts/ensure_goods_chain_indexes.py`, run in the background by
`start.sh` on every backend start. All of it lives in `app/utils/online_index.py`.

Revision ID: gc_idx_0001_spo_from_po_key
Revises: akc_0001_removed_unreferenced
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.utils.online_index import GOODS_CHAIN_KEY_INDEXES, ensure_indexes_online

revision = "gc_idx_0001_spo_from_po_key"
down_revision = "akc_0001_removed_unreferenced"
branch_labels = None
depends_on = None


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the SPO and PO syncs keep
    # writing both tables while it builds.
    with op.get_context().autocommit_block():
        ensure_indexes_online(op.get_bind(), GOODS_CHAIN_KEY_INDEXES)


def downgrade():
    with op.get_context().autocommit_block():
        for _table, name, _columns in GOODS_CHAIN_KEY_INDEXES:
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}"))
