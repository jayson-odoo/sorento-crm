"""Embedding company_id (multi-company data isolation, Part B).

Adds a nullable ``company_id`` to ``embedding_documents`` and ``embedding_chunks``
so RAG / semantic search can be restricted to the caller's company scope (AC-I4)
and fresh embeddings inherit their source entity's company (AC-I5). These are
pipeline tables, NOT owned business tables: they are NOT CompanyScopedMixin
subclasses (so the ORM ``do_orm_execute`` filter never touches them) - the vector
search injects the company predicate manually in ``EmbeddingReadService``.

The queue itself keeps no company_id column: the fresh-write path threads the
source's company_id through the queue JSON ``payload`` (listener copy) and the
worker also re-derives it from the loaded source row (it runs system-scoped, so
it can read any company). Backfill stamps existing embedding rows from their
source owned row where the source_type maps to an owned table; rows whose source
is synthetic / company-less (mcp_tool, form, schema_doc, conversation_frame,
order_status, ``debtor:`` seeds) stay NULL - those are shared knowledge and remain
visible under every scope.

Revision ID: 304_embedding_company
Revises: 303_import_job_company
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "304_embedding_company"
down_revision = "303_import_job_company"
branch_labels = None
depends_on = None

# source_type -> owned source table. source_id stores str(uuid) for these, so the
# backfill joins on ``source_id = <table>.id::text``. Types absent here are
# company-less / synthetic and are intentionally left NULL.
_SOURCE_TABLE = {
    "product": "products",
    "promotion": "promotions",
    "promotion_product": "promotion_products",
    "promotion_attachment": "promotion_attachments",
    "product_attachment": "product_attachments",
    "attachment": "attachments",
    "inbound_shipment": "inbound_shipments",
    "inbound_shipment_line": "inbound_shipment_lines",
    "spo_allocation": "spo_allocations",
    "picking_header": "picking_headers",
    "picking_line": "picking_lines",
    "order": "orders",
    "order_line": "order_lines",
    "customer": "customers",
    "transporter": "transporters",
}


def upgrade():
    for tbl in ("embedding_documents", "embedding_chunks"):
        op.execute(f"ALTER TABLE {tbl} ADD COLUMN IF NOT EXISTS company_id uuid")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{tbl}_company_id ON {tbl} (company_id)"
        )

    # Backfill existing embedding rows from their source owned row.
    for target in ("embedding_documents", "embedding_chunks"):
        for source_type, src_table in _SOURCE_TABLE.items():
            op.execute(
                f"""
                UPDATE {target} e
                SET company_id = s.company_id
                FROM {src_table} s
                WHERE e.source_type = '{source_type}'
                  AND e.source_id = s.id::text
                  AND e.company_id IS NULL
                  AND s.company_id IS NOT NULL
                """
            )


def downgrade():
    for tbl in ("embedding_documents", "embedding_chunks"):
        op.execute(f"DROP INDEX IF EXISTS ix_{tbl}_company_id")
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN IF EXISTS company_id")
