"""chatbot turn re-architecture S7: forms narrows on form (arms a numbered pick)

Item 1 (captain ruling, 17 Sep 2026): `chatbot_domains.forms.narrowing` was `{}`, so
`turn/apply.py::_narrow_and_plan` never called `narrow_decide` for this domain at all -
a picked form (`focus.extra["form"]`, written by `_answer_pending`'s generic roster
resolution) never reached the FetchSpec, whatever the MCP projection carried. "form:
must_narrow_one" is the same policy `chatbot_rearch_s6b` gave `product_attachment.
product`: a settled carry (the pick) passes straight through, several distinct forms
in play ask, one bare name is left to the resolver.

Revision ID: chatbot_rearch_s7
Revises: chatbot_rearch_s6f
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s7"
down_revision = "chatbot_rearch_s6f"
branch_labels = None
depends_on = None


def apply_narrowing(bind) -> None:
    """Set `forms.narrowing.form` to `must_narrow_one`.

    Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, for the same
    create_all-gap reason as `chatbot_rearch_s6d.apply_narrowing` /
    `chatbot_rearch_s6e.apply_narrowing`. Idempotent: a jsonb `||` merge with the same
    value is a no-op.
    """
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"form\": \"must_narrow_one\"}'::jsonb "
            "WHERE name = 'forms'"
        )
    )


def upgrade() -> None:
    apply_narrowing(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE chatbot_domains SET narrowing = narrowing - 'form' "
            "WHERE name = 'forms'"
        )
    )
