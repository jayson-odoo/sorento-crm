"""Per-contact + feature columns on ai_assistant_usage_logs.

Adds three nullable columns so the existing usage table can attribute spend
to portal contacts (no users.id) and discriminate between AI assistant chat
and AI extract pre-fill calls.

- contact_id: FK -> respond_contacts.id (Text PK), ON DELETE SET NULL.
  Stores the internal respond_contacts.id, NOT respond_io_id.
- feature: "ai_assistant" | "ai_extract" - discriminator for reporting.
- form_key: portal form key when feature="ai_extract" (e.g. "portal.complaint").

Existing rows remain valid (all three columns are nullable). The reporting
endpoints treat NULL feature as legacy AI assistant rows.

Revision ID: 166_ai_usage_contact_id
Revises: 165_respond_workspace_is_default
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa


revision = "166_ai_usage_contact_id"
down_revision = "165_respond_workspace_is_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_assistant_usage_logs",
        sa.Column("contact_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "ai_assistant_usage_logs",
        sa.Column("feature", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "ai_assistant_usage_logs",
        sa.Column("form_key", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_ai_assistant_usage_logs_contact_id_respond_contacts",
        "ai_assistant_usage_logs",
        "respond_contacts",
        ["contact_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_ai_assistant_usage_logs_contact_id",
        "ai_assistant_usage_logs",
        ["contact_id"],
    )
    op.create_index(
        "ix_ai_assistant_usage_logs_feature_created_at",
        "ai_assistant_usage_logs",
        ["feature", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ai_assistant_usage_logs_feature_created_at",
        table_name="ai_assistant_usage_logs",
    )
    op.drop_index(
        "ix_ai_assistant_usage_logs_contact_id",
        table_name="ai_assistant_usage_logs",
    )
    op.drop_constraint(
        "fk_ai_assistant_usage_logs_contact_id_respond_contacts",
        "ai_assistant_usage_logs",
        type_="foreignkey",
    )
    op.drop_column("ai_assistant_usage_logs", "form_key")
    op.drop_column("ai_assistant_usage_logs", "feature")
    op.drop_column("ai_assistant_usage_logs", "contact_id")
