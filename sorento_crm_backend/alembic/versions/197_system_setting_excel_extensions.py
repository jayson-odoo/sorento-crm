"""Add excel_upload_accept_extensions to system_settings.

Configurable comma-separated extension list (e.g. ".xlsx,.xls,.xlsm") consumed
by the Excel uploader UI/server validators. Default includes `.xlsm` - macro
workbooks are stripped on intake (see excel_macro_stripper).

Revision ID: 197_system_setting_excel_extensions
Revises: 196_drop_promotion_name
Create Date: 2026-05-15
"""
import sqlalchemy as sa
from alembic import op


revision = "197_system_setting_excel_extensions"
down_revision = "196_drop_promotion_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "system_settings",
        sa.Column(
            "excel_upload_accept_extensions",
            sa.String(length=255),
            nullable=False,
            server_default=".xlsx,.xls,.xlsm",
        ),
    )
    # Backfill: tenants whose default landed before .xlsm support shipped need
    # the macro-enabled extension appended so the uploader allowlist matches.
    op.execute(
        "UPDATE system_settings SET excel_upload_accept_extensions = '.xlsx,.xls,.xlsm' "
        "WHERE excel_upload_accept_extensions = '.xlsx,.xls'"
    )


def downgrade() -> None:
    op.drop_column("system_settings", "excel_upload_accept_extensions")
