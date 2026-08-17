"""How long a document read actually took.

The elapsed time was already measured in ``document_extraction`` and thrown away at the
end of the call. A reviewer who uploads a ten page scan waits minutes with no idea
whether it is working, and telling them afterwards what it cost is the cheapest way to
make the wait legible.

Revision ID: 320_extraction_elapsed_ms
Revises: 319_project_lead_to_so
"""
from alembic import op
import sqlalchemy as sa

revision = "320_extraction_elapsed_ms"
down_revision = "319_project_lead_to_so"
branch_labels = None
depends_on = None

_TABLES = ("project_po_versions", "delivery_schedule_versions")


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    # Idempotent: this branch and the main line share a dev database, so the column may
    # already be present from another worktree's run.
    for table in _TABLES:
        if not _has_column(table, "extraction_elapsed_ms"):
            op.add_column(table, sa.Column("extraction_elapsed_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        if _has_column(table, "extraction_elapsed_ms"):
            op.drop_column(table, "extraction_elapsed_ms")
