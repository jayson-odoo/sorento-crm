"""import_job_rows: per-row outcome capture for every import job

Chained onto main's single head ``cbf3a0044924`` (the merge of the promo-expiry
and integration chains), NOT the in-flight multi-company chain (302..306), so
this ships independently. Re-check ``alembic heads`` after any merge from main:
a second head makes ``upgrade head`` fail to resolve at deploy time, which is
exactly what this migration hit once already.

See documentation/plans/imports/PLAN-import-job-row-outcomes.md §2.1/§2.7.

Revision ID: 307_import_job_rows
Revises: cbf3a0044924
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "307_import_job_rows"
down_revision = "cbf3a0044924"
branch_labels = None
depends_on = None


def _add_retention_setting(inspector) -> None:
    """Retention window for the per-row detail (counts/breakdown never prune)."""
    if "system_settings" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("system_settings")}
    if "import_job_rows_retention_days" in existing:
        return
    op.add_column(
        "system_settings",
        sa.Column(
            "import_job_rows_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _add_retention_setting(inspector)
    if "import_job_rows" in inspector.get_table_names():
        # Idempotent: the branch may be applied on an environment that already
        # ran it via create_all (first-install path).
        return

    op.create_table(
        "import_job_rows",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("import_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("value", sa.String(length=255), nullable=True),
        sa.Column("identity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["import_job_id"], ["import_jobs.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_import_job_rows_import_job_id", "import_job_rows", ["import_job_id"]
    )
    op.create_index(
        "ix_import_job_rows_job_outcome", "import_job_rows", ["import_job_id", "outcome"]
    )
    op.create_index(
        "ix_import_job_rows_job_code", "import_job_rows", ["import_job_id", "code"]
    )
    op.create_index(
        "ix_import_job_rows_job_row", "import_job_rows", ["import_job_id", "row_number"]
    )
    # Retention sweep deletes by age, so this index carries the prune.
    op.create_index("ix_import_job_rows_created_at", "import_job_rows", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "import_job_rows" not in inspector.get_table_names():
        return
    for name in (
        "ix_import_job_rows_created_at",
        "ix_import_job_rows_job_row",
        "ix_import_job_rows_job_code",
        "ix_import_job_rows_job_outcome",
        "ix_import_job_rows_import_job_id",
    ):
        try:
            op.drop_index(name, table_name="import_job_rows")
        except Exception:
            pass
    op.drop_table("import_job_rows")
