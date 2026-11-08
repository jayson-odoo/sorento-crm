"""Seed the `ai_assistant_attachment` attachment type (AGENT-PANEL-COMPOSER).

Files a staff member attaches to an AI assistant message: images, Excel, CSV and PDF, up to 10 MB each and
5 unsent per user. Idempotent, and a hand-edited type is left as the admin set it.

Revision ID: panel_att_0001_ai_asst_type
Revises: qcert_0001_quote_certificates
"""
from alembic import op
import sqlalchemy as sa

revision = "panel_att_0001_ai_asst_type"
down_revision = "qcert_0001_quote_certificates"
branch_labels = None
depends_on = None

CODE = "ai_assistant_attachment"
NAME = "AI assistant attachment"


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT 1 FROM attachment_types WHERE code = :code OR type_name = :name LIMIT 1"),
        {"code": CODE, "name": NAME},
    ).first()
    if exists:
        return
    # No n8n intake: a draft would otherwise show in the upload-activity list and sit on Processing.
    has_webhook = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'attachment_types' AND column_name = 'triggers_n8n_webhook'"
        )
    ).first()
    webhook_col = ", triggers_n8n_webhook" if has_webhook else ""
    webhook_val = ", false" if has_webhook else ""
    # `id` is explicit: a create_all-built schema has no server default for it.
    bind.execute(
        sa.text(
            "INSERT INTO attachment_types "
            f"(id, code, type_name, description, allowed_extensions, max_file_size_mb, max_count_per_entity{webhook_col}) "
            f"VALUES (gen_random_uuid(), :code, :name, :description, :exts, 10, 5{webhook_val})"
        ),
        {
            "code": CODE,
            "name": NAME,
            "description": "Files staff attach to a message to the AI assistant.",
            "exts": "png,jpg,jpeg,webp,xlsx,xls,csv,pdf",
        },
    )


def downgrade() -> None:
    pass
