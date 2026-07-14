"""Retain original uploaded file per import job (source-file tracing).

Adds nullable source-file columns to import_jobs so the raw uploaded bytes can be
persisted to the storage bucket and downloaded later from Import Job Details.

Revision ID: 272_import_source_file
Revises: 271_audit_action_allow_import
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa


revision = "272_import_source_file"
down_revision = "271_audit_action_allow_import"
branch_labels = None
depends_on = None


_COLUMNS = (
    ("source_filename", sa.String()),
    ("source_file_key", sa.String()),
    ("source_file_provider", sa.String()),
    ("source_file_size", sa.Integer()),
)


def _existing_columns(bind) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns("import_jobs")}


def upgrade() -> None:
    existing = _existing_columns(op.get_bind())
    for name, col_type in _COLUMNS:
        if name not in existing:
            op.add_column("import_jobs", sa.Column(name, col_type, nullable=True))


def downgrade() -> None:
    existing = _existing_columns(op.get_bind())
    for name, _ in reversed(_COLUMNS):
        if name in existing:
            op.drop_column("import_jobs", name)
