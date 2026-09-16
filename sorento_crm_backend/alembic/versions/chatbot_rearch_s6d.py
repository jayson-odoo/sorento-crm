"""chatbot turn re-architecture S6d: the order product filters, the purchase cost lists all

Owner hand pass 2 (17 Sep 2026), items 6 and 3.

Item 6, turn c45e2929 ("Outstsnding DO for 7445"): `chatbot_domains.order.narrowing` named
the customer and nothing else, so a product token on an order ask reached the narrower
under no policy at all, contributed no entity and no filter, and the outstanding report
ran over every product under a header that read `Product: all`. `optional_filter` is the
policy that says what the owner ruled: the token resolves and filters the answer, and it
is never silently dropped.

Item 3, turn 70be252c ("Last purchase cost for srtwc286"): `purchase_cost` carried
`product: narrow_to_code`, so a family of variants was a picker before the answer. The
owner ruled the cost answer lists every variant, the same way `inventory` does.

Both stay editable on the Chatbot Domains page; this only moves the seed.

Revision ID: chatbot_rearch_s6d
Revises: chatbot_rearch_s6c
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6d"
down_revision = "chatbot_rearch_s6c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"optional_filter\"}'::jsonb "
            "WHERE name = 'order'"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"list_all\"}'::jsonb "
            "WHERE name = 'purchase_cost'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE chatbot_domains SET narrowing = narrowing - 'product' WHERE name = 'order'")
    )
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"narrow_to_code\"}'::jsonb "
            "WHERE name = 'purchase_cost'"
        )
    )
