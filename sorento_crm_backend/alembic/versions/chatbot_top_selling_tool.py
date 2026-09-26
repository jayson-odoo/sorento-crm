"""chatbot: the order domain claims `crm_top_selling_report`

PLAN-chatbot-top-x-hot-selling-24sep.md, slice S3 (AC-1941), the same shape as
`chatbot_rearch_s9` (which did this for `crm_sales_report`). The tool is appended to the
order row's `tools` so the owner-facing Chatbot Domains screen and the frozen seed in
`turn/policy_rows.py` agree; the allow-list itself (`fetch.CHATBOT_READ_ONLY_TOOLS`) is
derived from that frozen seed, not from this row. Never `tools[0]`: the pick is the S4
override in `lanes/business/__init__.py::run_fetch`.

`chatbot_parser_prompt.domain_line` does not render `tools`, so `prompt_blocks_hash` is
unmoved and no republish follows from this migration.

Revision ID: chatbot_top_selling_tool
Revises: sb3_company_stock_push_at
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "chatbot_top_selling_tool"
down_revision = "sb3_company_stock_push_at"
branch_labels = None
depends_on = None

TOOL = "crm_top_selling_report"


def apply_tools(bind) -> None:
    """Append the tool to the order domain's `tools` (a `text[]`), once. Shared by
    `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`, as `chatbot_rearch_s9`'s
    applier is."""
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
