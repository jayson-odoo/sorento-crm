"""chatbot turn re-architecture S8: purchase cost with no product asks, never errors

Defect 6 (owner hand pass 6, 17 Sep 2026): `purchase_cost.narrowing.product` was
`list_all` (S6d, item 3 - "the cost answer LISTS every variant"), so a "purchase
cost" turn naming NO product at all narrowed to `entities: []` and the fetch reached
`crm_procurement_po_last_cost_list` with no filter. That tool is one of
`policy_rows.ENTITY_FILTER_REQUIRED_TOOLS`, so the call was refused
("...needs a document or entity filter and none could be built", outcome
"not_found") - and `turn_runtime.envelope_of` reads `fragment["error"]` unconditionally
(it never special-cases `outcome == "not_found"` the way it already does for
"access_denied"), so the customer read "I could not fetch last purchase cost just
now, please try again" about a MISSING ENTITY, not a broken tool.

"narrow_by_type" is the existing policy value that already asks (`{kind}_ask`) when
`_candidates` comes back empty and passes carried/resolved rows straight through
otherwise (`turn/narrow.py::decide`, the `_TYPE_POLICIES` branch) - today only read
for the `attachment_type` kind. Reusing it for `purchase_cost.product` needs no new
narrowing value and no new engine code: a "purchase cost" with no product in play now
asks "Which product do you mean?" (`turn/compose.py::_ASK_HEADERS["product_ask"]`)
instead of reaching the tool at all.

Revision ID: chatbot_rearch_s8
Revises: chatbot_rearch_s7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s8"
down_revision = "chatbot_rearch_s7"
branch_labels = None
depends_on = None


def apply_narrowing(bind) -> None:
    """Set `purchase_cost.narrowing.product` to `narrow_by_type`.

    Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, for the same
    create_all-gap reason as `chatbot_rearch_s6d`/`s6e`/`s7`'s own `apply_narrowing`.
    Idempotent: a jsonb `||` merge with the same value is a no-op.
    """
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"narrow_by_type\"}'::jsonb "
            "WHERE name = 'purchase_cost'"
        )
    )


def upgrade() -> None:
    apply_narrowing(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET narrowing = narrowing || '{\"product\": \"list_all\"}'::jsonb "
            "WHERE name = 'purchase_cost'"
        )
    )
