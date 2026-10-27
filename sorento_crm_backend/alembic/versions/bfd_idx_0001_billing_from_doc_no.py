"""Index finance.billing_document_lines.from_doc_no (BILLING-FROM-DOC-INDEX).

``documentation/plans/finance/PLAN-billing-from-doc-index-27oct.md``. DOC-RELATIONS (#1912)
finds an SO's / DO's billing documents, and the billing list filters by sales order, through
``from_doc_no`` (``app/services/document_relations.py`` billing_ids_for_sales_order /
billing_ids_for_delivery_order), which had no index: every SO / DO detail view read the whole
lines table.

Built like ``gc_idx_0001_spo_from_po_key``: CONCURRENTLY under the repo's migration limits, and a
build that times out or fails logs a WARNING and lets this revision SUCCEED with the index
missing; ``scripts/ensure_goods_chain_indexes.py`` (run in the background by ``start.sh``)
retries it. All of it lives in ``app/utils/online_index.py``.

Revision ID: bfd_idx_0001_billing_from_doc_no
Revises: sales_unified_0002
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.utils import online_index

revision = "bfd_idx_0001_billing_from_doc_no"
down_revision = "sales_unified_0002"
branch_labels = None
depends_on = None


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the billing sync keeps
    # writing the table while it builds.
    with op.get_context().autocommit_block():
        online_index.ensure_indexes_online(op.get_bind(), online_index.BILLING_FROM_DOC_INDEXES)


def downgrade():
    with op.get_context().autocommit_block():
        for table, name, _columns in online_index.BILLING_FROM_DOC_INDEXES:
            qualified = online_index._qualified(table, name)
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {qualified}"))
