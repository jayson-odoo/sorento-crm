"""Add forms.form_type default marketing for legacy forms management.

Revision ID: 149_forms_form_type
Revises: 148_chat_histories_contact_id_to_string
"""

from alembic import op
import sqlalchemy as sa


revision = "149_forms_form_type"
down_revision = "148_chat_histories_contact_id_to_string"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "forms",
        sa.Column(
            "form_type",
            sa.String(length=64),
            nullable=False,
            server_default="marketing",
        ),
    )
    op.execute("UPDATE forms SET form_type = 'marketing' WHERE form_type IS NULL OR form_type = ''")
    op.create_index("ix_forms_form_type", "forms", ["form_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_forms_form_type", table_name="forms")
    op.drop_column("forms", "form_type")
