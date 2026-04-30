"""Add session_vars JSONB column to respond_contacts.

Revision ID: 156_respond_contacts_session_vars
Revises: 155_products_dimensions_reparse

Holds per-Respond.io-contact conversation variables collected from n8n turns,
shaped {"turns":[{ts,inquiry_type,vars}], "merged":{<inquiry_type>:{...}}}.
Maintained by POST /api/v1/external/conversation-variables/upsert.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "156_respond_contacts_session_vars"
down_revision = "155_products_dimensions_reparse"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "respond_contacts",
        sa.Column(
            "session_vars",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        "UPDATE respond_contacts SET session_vars = '{}'::jsonb WHERE session_vars IS NULL"
    )


def downgrade() -> None:
    op.drop_column("respond_contacts", "session_vars")
