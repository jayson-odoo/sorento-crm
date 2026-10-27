"""chatbot: the three retired sales and outstanding tools leave the `order` and `sales` rows

PLAN-report-unify-27oct.md, section 2 (owner ruling Q1). Every sales total, breakdown and
outstanding ask now runs on `crm_report_ask`, so no chatbot path reaches `crm_sales_report` or
`crm_outstanding_report` any more; `crm_sales_analysis` is reached only by the Yearly comparison
(axis year), a `run_fetch` override that needs no row. All three are removed from every
`chatbot_domains.tools` row that lists them, so the Chatbot Domains screen agrees with the frozen
seed in `turn/policy_rows.py` (the allow-list itself is derived from that seed). The routes, the
MCP tools and the analytics connector keep them.

`chatbot_parser_prompt.domain_line` does not render `tools`, so `prompt_blocks_hash` is
unmoved and no republish follows from this migration.

Revision ID: report_unify_0001_retire
Revises: resub_0001_resubmitted_status
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "report_unify_0001_retire"
down_revision = "resub_0001_resubmitted_status"
branch_labels = None
depends_on = None

RETIRED = ("crm_sales_report", "crm_outstanding_report", "crm_sales_analysis")


def apply_tools(bind) -> None:
    """Idempotent. Shared by `upgrade()` and `scripts.bootstrap_env.seed_chatbot_policy`."""
    for tool in RETIRED:
        bind.execute(
            sa.text(
                "UPDATE chatbot_domains SET tools = array_remove(tools, CAST(:tool AS text)) "
                "WHERE CAST(:tool AS text) = ANY(tools)"
            ),
            {"tool": tool},
        )


def upgrade() -> None:
    apply_tools(op.get_bind())


def downgrade() -> None:
    """The seed had `crm_outstanding_report` on the order row, and the two sales tools on both the
    order and sales rows; appended last, so `tools[0]` is unchanged."""
    bind = op.get_bind()
    for tool, rows in (
        ("crm_outstanding_report", ("order",)),
        ("crm_sales_report", ("order", "sales")),
        ("crm_sales_analysis", ("order", "sales")),
    ):
        bind.execute(
            sa.text(
                "UPDATE chatbot_domains SET tools = array_append(tools, CAST(:tool AS text)) "
                "WHERE name = ANY(CAST(:rows AS text[])) AND NOT (CAST(:tool AS text) = ANY(tools))"
            ),
            {"tool": tool, "rows": list(rows)},
        )
