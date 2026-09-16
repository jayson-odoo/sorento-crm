"""chatbot turn re-architecture S6e: a promotion question is about a product too

Browser pass 6 (18 Sep 2026), item 1, turns cc0494a1 and 0bd47e62. "Promo for srtwc286"
asked the price tier and "1" answered it, and the promotion fetch that followed carried
`entities: []` - no product at all - because `chatbot_domains.promotion.narrowing` named
the tier and nothing else, so a product token on a promotion ask reached the narrower
under no policy, contributed no entity and no filter, and was silently dropped.

`optional_filter` is the same policy the `order` domain carries for the same reason
(s6d): the token resolves and filters the answer, an ambiguous token THIS message named
asks its roster (with the has promo / no promo stamps the S6 ruling asks for), and a
carried token is never re-asked - the tier pick settles the tier, and the product goes
on to the fetch. `list_all` was the alternative and is the owner's to choose on the
Chatbot Domains page; this only moves the seed.

Revision ID: chatbot_rearch_s6e
Revises: chatbot_rearch_s6d
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s6e"
down_revision = "chatbot_rearch_s6d"
branch_labels = None
depends_on = None


def apply_narrowing(bind) -> None:
    """Set `promotion.narrowing.product` to `optional_filter`.

    Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, for the same
    create_all-gap reason as `chatbot_rearch_s6d.apply_narrowing`. Idempotent: a jsonb
    `||` merge with the same value is a no-op.
    """
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"optional_filter\"}'::jsonb "
            "WHERE name = 'promotion'"
        )
    )


def upgrade() -> None:
    apply_narrowing(op.get_bind())


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains SET narrowing = narrowing - 'product' "
            "WHERE name = 'promotion'"
        )
    )
