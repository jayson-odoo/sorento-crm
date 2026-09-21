"""chatbot turn re-architecture S9: the order domain claims `crm_sales_report`

PLAN-chatbot-sales-report.md S4 wiring point 3, ported onto the policy TABLE this lane
moved `contracts.DOMAIN_SPEC` into (S0, AC-1501). The sales report lane added the tool
to the order domain's `tools` tuple in `contracts.py`; here that tuple is the
`chatbot_domains.tools` column, seeded from `turn/policy_rows.py`.

The tool name is an ALLOW-LIST member only, never `tools[0]`: the pick is an override in
`lanes/business/__init__.py::run_fetch` (domain "order" + a resolved product or customer
+ `order_status: "sales_report"`). The allow-list itself
(`lanes/business/fetch.CHATBOT_READ_ONLY_TOOLS`) is derived from the FROZEN seed in
`policy_rows.py`, not from this row, on purpose - it is a security boundary and an owner
editing the table must not widen it. This migration exists so the owner-facing table and
the frozen seed do not drift: the Chatbot Domains screen reads this column, and an order
row that did not list the report would show an incomplete tool set for the domain.

No narrowing change and no prompt-block change (`chatbot_parser_prompt.domain_line` does
not render `tools`), so `prompt_blocks_hash` is unmoved and no republish follows from
this migration alone.

Revision ID: chatbot_rearch_s9
Revises: chatbot_rearch_s8
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_rearch_s9"
down_revision = "chatbot_rearch_s8"
branch_labels = None
depends_on = None

TOOL = "crm_sales_report"


def apply_tools(bind) -> None:
    """Append `crm_sales_report` to the order domain's `tools`, once.

    Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, for the same
    create_all-gap reason as `chatbot_rearch_s6d`/`s6e`/`s7`/`s8`'s own appliers. The
    `= ANY` guard makes it idempotent.

    `tools` is a Postgres `text[]`, NOT jsonb - unlike `narrowing` and `ladder` on the
    same table, which the sibling migrations merge with `||` on jsonb. `CAST(:tool AS
    text)` rather than `:tool::text`: SQLAlchemy reads the `::` form as no parameter
    at all and leaves the literal `:tool` in the statement.
    """
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET tools = array_append(tools, CAST(:tool AS text)) "
            "WHERE name = 'order' AND NOT (CAST(:tool AS text) = ANY(tools))"
        ),
        {"tool": TOOL},
    )


def upgrade() -> None:
    apply_tools(op.get_bind())


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE chatbot_domains "
            "SET tools = array_remove(tools, CAST(:tool AS text)) "
            "WHERE name = 'order' AND CAST(:tool AS text) = ANY(tools)"
        ),
        {"tool": TOOL},
    )
