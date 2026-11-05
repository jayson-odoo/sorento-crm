"""PO-LINK-HISTORY: no-op. The "first seen" backfill runs after the backend starts.

POLH-BACKFILL-ASYNC (5 Nov 2026): this revision used to seed one ``scm.po_line.book_so_seen``
audit event per linked PO line inside the deploy's single migration transaction. On the prod
clone one 5,000-line batch took 18.7 s (a Seq Scan of ``scm.order_link_claim`` per line), so
the 5 Nov release passed blue/green's 240 s health wait and every pending revision rolled back.
It never committed on production, so it is emptied in place and the chain is unchanged.

The data step is ``app.services.scm.po_link_history.backfill_seen``, run in the background by
``start.sh`` (``python -m scripts.backfill_po_link_seen &``): one commit per batch, resumable,
idempotent, advisory-locked. Plan: documentation/plans/procurement/PLAN-polh-backfill-async-05nov.md.

Revision ID: polh_0001_seen_backfill
Revises: oiod_0001_backfill
"""
revision = "polh_0001_seen_backfill"
down_revision = "oiod_0001_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Data only, and that data now loads after start (see the docstring). No DDL.
    pass


def downgrade() -> None:
    pass
