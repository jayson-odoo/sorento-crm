"""mcp_tools.chatbot_domain: the tool pool is chosen by DATA, not by the tool name.

Owner ruling (8 Sep 2026, "I don't accept the leak"): `search_tool_chunks` narrowed a
domain's candidate tools with `source_id LIKE '%<domain>%'` over the tool NAME. The PO
placed tool's old name, `crm_procurement_purchase_orders_placed_list`, contained "order",
so it entered every `order` pool (measured 0.36-0.38 similarity against the orders list's
0.43) even though it belongs to `purchase_order`. Two independent fixes landed together:
that ONE tool was renamed to `crm_procurement_po_placed_list`, a name no domain's
substring matches (so n8n's own untouched `LIKE` query never picks it either); THIS
column is the systemic fix, so no other tool needs a name chosen around a filter that
reads it.

`chatbot_domain` is stamped by `mcp_tool_registry_service.sync_catalog` from
`app.services.chatbot.contracts.DOMAIN_SPEC`: a tool listed under one domain's `tools`
gets that domain; a tool in no domain's list gets NULL (never enters a chatbot pool).
NULL default so every existing tool row stays inert until the next sync.

Revision ID: 492_mcp_tool_chatbot_domain
Revises: 491_chatbot_ladder_incoming_po
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "492_mcp_tool_chatbot_domain"
down_revision = "491_chatbot_ladder_incoming_po"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("mcp_tools")}
    if "chatbot_domain" not in columns:
        op.add_column(
            "mcp_tools",
            sa.Column("chatbot_domain", sa.String(64), nullable=True),
        )
        op.create_index(
            "ix_mcp_tools_chatbot_domain",
            "mcp_tools",
            ["chatbot_domain"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("mcp_tools")}
    if "chatbot_domain" in columns:
        op.drop_index("ix_mcp_tools_chatbot_domain", table_name="mcp_tools")
        op.drop_column("mcp_tools", "chatbot_domain")
