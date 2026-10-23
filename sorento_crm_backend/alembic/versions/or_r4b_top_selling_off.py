"""chatbot: `crm_top_selling_report` leaves every domain, the sales domain claims `crm_report_ask`

PLAN-one-ranking-1023.md, round R4b (AC-OR4). Since R1 every ranking ask (items, categories,
customers, agents, ...) runs on `crm_report_ask`, so no chatbot path reaches the top selling
tool any more. The tool is removed from every `chatbot_domains.tools` row that lists it and
`crm_report_ask` is appended to the `sales` row (the order row already has it, from
`report_engine_0001_prompt`), so the Chatbot Domains screen agrees with the frozen seed in
`turn/policy_rows.py`; the allow-list itself is derived from that seed, not from these rows.
The route, the MCP tool and the analytics connector keep the tool.

`chatbot_parser_prompt.domain_line` does not render `tools`, so `prompt_blocks_hash` is
unmoved and no republish follows from this migration.

Revision ID: or_r4b_top_selling_off
Revises: npa_0002_paper_layout
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "or_r4b_top_selling_off"
down_revision = "npa_0002_paper_layout"
branch_labels = None
depends_on = None

OLD = "crm_top_selling_report"
ASK = "crm_report_ask"


def apply_tools(bind) -> None:
    """Idempotent. Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`."""
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains SET tools = array_remove(tools, CAST(:old AS text)) "
            "WHERE CAST(:old AS text) = ANY(tools)"
        ),
        {"old": OLD},
    )
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains SET tools = array_append(tools, CAST(:ask AS text)) "
            "WHERE name = 'sales' AND NOT (CAST(:ask AS text) = ANY(tools))"
        ),
        {"ask": ASK},
    )


def upgrade() -> None:
    apply_tools(op.get_bind())


def downgrade() -> None:
    """The seeded policy had the tool on the order and sales rows, but the upgrade does not record
    which rows lost it, so the tool goes back on every row that lacks it (what the migration test
    pins); the sales row drops `crm_report_ask`, the order row keeps its own."""
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains SET tools = array_append(tools, CAST(:old AS text)) "
            "WHERE NOT (CAST(:old AS text) = ANY(tools))"
        ),
        {"old": OLD},
    )
    bind.execute(
        sa.text(
            "UPDATE chatbot_domains SET tools = array_remove(tools, CAST(:ask AS text)) WHERE name = 'sales'"
        ),
        {"ask": ASK},
    )
