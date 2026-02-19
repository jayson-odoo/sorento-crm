"""Add updated_at to import_jobs

Revision ID: 044_import_jobs_updated_at
Revises: 043_dir_soft_delete
Create Date: 2026-02-15

"""
from alembic import op
import sqlalchemy as sa


revision = "044_import_jobs_updated_at"
down_revision = "043_dir_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_jobs",
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=True),
    )
    # Set updated_at = completed_at for finished jobs, started_at for started, created_at for pending
    op.execute("""
        UPDATE import_jobs
        SET updated_at = COALESCE(completed_at, started_at, created_at)
    """)


def downgrade() -> None:
    op.drop_column("import_jobs", "updated_at")
