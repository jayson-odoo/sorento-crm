"""Index embedding_chunks (model_name, document_id) WHERE is_current (EMBED-PAGE-PERF).

``documentation/plans/system/PLAN-embed-page-perf-30oct.md``. The Embeddings overview (Records tab, refetched every
30 s) and the backfill guard count active documents with no current chunk of a model
(``app/services/embedding_backfill_service.py`` _MISSING_SQL). No index held both the model and the document, so each
probe read the chunk heap, which keeps every superseded and old-model chunk with its vector and text.

Built like ``bfd_idx_0001_billing_from_doc_no``: CONCURRENTLY under the repo's migration limits, and a build that
times out or fails logs a WARNING and lets this revision SUCCEED with the index missing;
``scripts/ensure_goods_chain_indexes.py`` (run in the background by ``start.sh``) retries it.

Revision ID: epp_0001_chunk_coverage_idx
Revises: qca1_0001_amendment_requests
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.services import embedding_indexes
from app.utils import online_index

revision = "epp_0001_chunk_coverage_idx"
down_revision = "qca1_0001_amendment_requests"
branch_labels = None
depends_on = None


def upgrade():
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction: the embedding worker keeps writing the table.
    with op.get_context().autocommit_block():
        online_index.ensure_indexes_online(op.get_bind(), embedding_indexes.COVERAGE_INDEXES)


def downgrade():
    with op.get_context().autocommit_block():
        for table, name, _columns in embedding_indexes.COVERAGE_INDEXES:
            qualified = online_index._qualified(table, name)
            op.get_bind().execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {qualified}"))
