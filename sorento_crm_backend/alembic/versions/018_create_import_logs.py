"""Create import_logs table

Revision ID: 018_create_import_logs
Revises: 017_add_order_tracking_columns
Create Date: 2026-01-24 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "018_create_import_logs"
down_revision = "017_add_order_tracking_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "import_logs" not in tables:
        op.create_table(
            "import_logs",
            sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("import_session_id", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=50), nullable=False),
            sa.Column("entity_table", sa.String(length=100), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("import_type", sa.String(length=50), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("successful_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("imported_by", sa.String(), nullable=True),
            sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )

        op.create_index("ix_import_logs_entity_type", "import_logs", ["entity_type"])
        op.create_index("ix_import_logs_entity_table", "import_logs", ["entity_table"])
        op.create_index("ix_import_logs_import_session_id", "import_logs", ["import_session_id"])
        op.create_index("ix_import_logs_imported_by", "import_logs", ["imported_by"])
        op.create_index("ix_import_logs_imported_at", "import_logs", ["imported_at"])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()

    if "import_logs" in tables:
        for index in inspector.get_indexes("import_logs"):
            if index["name"].startswith("ix_import_logs"):
                op.drop_index(index["name"], table_name="import_logs")
        op.drop_table("import_logs")
