"""chatbot turn re-architecture S6: stock allowance is a CRM fact on the contact row

Owner ruling (hand-pass 1, 16 Sep 2026): whether a contact may ask for stock is the
CRM's own fact, default ON for everyone; the respond.io `is_allowed_stock` custom field
is no longer read. Measured on the clone: a console turn borrowed an envelope whose
`custom_fields` was `[]`, the engine read the missing field as "not allowed" and answered
"check stock srtwc286" with the demand-quantity ask. A column on `respond_contacts`
beside `chatbot_recall_enabled` is the one place the fact lives; the Contact > Access
"Chatbot" card edits it.

Revision ID: chatbot_rearch_s6
Revises: chatbot_rearch_s5
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6"
down_revision = "chatbot_rearch_s5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "respond_contacts",
        sa.Column(
            "chatbot_stock_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("respond_contacts", "chatbot_stock_allowed")
