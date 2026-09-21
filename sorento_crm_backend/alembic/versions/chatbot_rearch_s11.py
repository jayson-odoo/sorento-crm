"""chatbot turn re-architecture S11: order domain narrows on the order axis too

Hand pass 12, Group B (owner ruling): a did-you-mean pick over an order token
(`focus.extra["order"]`/`["customer_order"]`, `EXTRA_KIND_ALIASES` in
`turn/state.py`) never reached the order tool - the "order" domain's own
`narrowing` had a "customer" and a "product" row and no "order" row at all, so
`turn/narrow.py::decide`'s `just_picked` shortcut had nothing to fire for and the
picked uuid never became a fetch entity (live trace: `entities_in: 0`). The same
`narrow_to_code` policy value `incoming`/`purchase_order` already give their own
`product` kind.

Revision ID: chatbot_rearch_s11
Revises: chatbot_rearch_s10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s11"
down_revision = "chatbot_rearch_s10"
branch_labels = None
depends_on = None


def apply_narrowing(bind) -> None:
    """Set `order.narrowing.order`.

    Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, the same
    convention `chatbot_rearch_s6d::apply_narrowing` set: a `create_all`-built
    database gets S0's original seed (no "order" key at all) and never runs this
    migration's UPDATE body otherwise. Idempotent: a jsonb `||` merge with the same
    value is a no-op.
    """
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"order\": \"narrow_to_code\"}'::jsonb "
            "WHERE name = 'order'"
        )
    )


def upgrade() -> None:
    apply_narrowing(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("UPDATE chatbot_domains SET narrowing = narrowing - 'order' WHERE name = 'order'")
    )
