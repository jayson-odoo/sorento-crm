"""NPA-FROM-SI: purchasing's "NPA needed" flag on the stock inquiry + an NPA line's current codes.

Additive only and idempotent (`IF NOT EXISTS`) so the shared dev DB, which converges through
`create_all`, can take it in any order. Nothing is dropped or rewritten.

- `stock_inquiries.npa_requested` (+ who / when): purchasing asks the salesperson to create a
  New Product Application on its reply. Non-blocking.
- `new_product_application_line_sources`: the CURRENT product codes a line's new code is based
  on (lineage current codes -> new code; the line's `opened_product_id` is the new code).

Card: documentation/plans/procurement/CARD-npa-from-si-07nov.md.

Revision ID: npasi_0001_lineage
Revises: slb_0001_leaderboard_perm
"""
import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "npasi_0001_lineage"
down_revision = "slb_0001_leaderboard_perm"
branch_labels = None
depends_on = None

UPGRADE = (
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested_by VARCHAR(100) "
    "REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE stock_inquiries ADD COLUMN IF NOT EXISTS npa_requested_at TIMESTAMP",
    """
    CREATE TABLE IF NOT EXISTS new_product_application_line_sources (
        id UUID PRIMARY KEY,
        line_id UUID NOT NULL REFERENCES new_product_application_lines(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
        position INTEGER NOT NULL DEFAULT 1,
        CONSTRAINT uq_npa_line_sources_line_product UNIQUE (line_id, product_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_npa_line_sources_product "
    "ON new_product_application_line_sources (product_id)",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UPGRADE:
        bind.execute(sa.text(statement))


def downgrade() -> None:
    bind = op.get_bind()
    for statement in (
        "DROP TABLE IF EXISTS new_product_application_line_sources",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested_at",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested_by",
        "ALTER TABLE stock_inquiries DROP COLUMN IF EXISTS npa_requested",
    ):
        bind.execute(sa.text(statement))
