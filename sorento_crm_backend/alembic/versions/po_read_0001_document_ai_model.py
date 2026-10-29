"""PO-READ-MODEL: the document reader's provider and model live in System Settings

Revision ID: po_read_0001_document_ai_model
Revises: chan_alias_0001_sales_channel
Create Date: 2026-10-29 00:00:00.000000

Prod, 29 Oct 2026: every PO upload failed "No page of this document could be read". The
reader took its model only from DOCUMENT_AI_MODEL (default gemini-2.5-flash) and the prod
Gemini key belongs to a new Google account, which gets a 404 on that model.

Adds `system_settings.document_ai_provider` / `document_ai_model` (nullable, the same shape
as `media_image_provider` / `media_image_model`) and seeds the existing row with gemini /
gemini-3.5-flash, the model photo reading already runs on in prod. A value an operator has
already saved is never overwritten. Additive and idempotent; downgrade drops the columns.
"""
from alembic import op

revision = "po_read_0001_document_ai_model"
down_revision = "chan_alias_0001_sales_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS document_ai_provider TEXT")
    op.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS document_ai_model TEXT")
    op.execute(
        "UPDATE system_settings SET document_ai_provider = 'gemini', "
        "document_ai_model = 'gemini-3.5-flash' "
        "WHERE document_ai_provider IS NULL AND document_ai_model IS NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS document_ai_model")
    op.execute("ALTER TABLE system_settings DROP COLUMN IF EXISTS document_ai_provider")
