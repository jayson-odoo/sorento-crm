"""Create import_jobs table

Revision ID: 020_create_import_jobs_table
Revises: 019_create_stock_ledger_table
Create Date: 2026-01-28 22:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "020_create_import_jobs_table"
down_revision = "019_create_stock_ledger_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "import_jobs" not in tables:
        op.create_table(
            "import_jobs",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("job_id", sa.String(), nullable=False, unique=True),
            sa.Column("job_type", sa.String(), nullable=False),
            sa.Column("status", sa.Enum("pending", "queued", "started", "finished", "failed", "cancelled", name="jobstatus"), nullable=False, server_default="pending"),
            sa.Column("user_id", sa.String(), nullable=False),
            sa.Column("filename", sa.String(), nullable=True),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("successful_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("result", postgresql.JSONB(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", postgresql.JSONB(), nullable=True),  # Column name is 'metadata', but model attribute is 'job_metadata'
        )
        
        # Create indexes
        op.create_index("ix_import_jobs_job_id", "import_jobs", ["job_id"])
        op.create_index("ix_import_jobs_status", "import_jobs", ["status"])
        op.create_index("ix_import_jobs_user_id", "import_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_import_jobs_user_id", table_name="import_jobs")
    op.drop_index("ix_import_jobs_status", table_name="import_jobs")
    op.drop_index("ix_import_jobs_job_id", table_name="import_jobs")
    op.drop_table("import_jobs")
    op.execute("DROP TYPE IF EXISTS jobstatus")
