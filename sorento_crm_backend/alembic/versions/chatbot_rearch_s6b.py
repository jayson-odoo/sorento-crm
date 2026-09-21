"""chatbot turn re-architecture S6b: product_attachment narrows on the product too

Owner ruling (hand-pass 1, finding 4, 16 Sep 2026): `chatbot_domains.product_attachment.
narrowing` was `{attachment_type: narrow_by_type}` only, so a document ask that named
several products ("photo for wc286", ten real siblings) never asked which one - the
fetch went out for all of them. `product: must_narrow_one` is the same policy the order
domain applies to its customer: a settled carry passes, several distinct names ask, one
bare name is left to the resolver.

Revision ID: chatbot_rearch_s6b
Revises: chatbot_rearch_s6
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6b"
down_revision = "chatbot_rearch_s6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"must_narrow_one\"}'::jsonb "
            "WHERE name = 'product_attachment'"
        )
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE chatbot_domains SET narrowing = narrowing - 'product' "
            "WHERE name = 'product_attachment'"
        )
    )
