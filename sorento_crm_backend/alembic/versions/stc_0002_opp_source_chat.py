"""Sales opportunities logged over the chat carry source 'chat' (SALES-TARGET-CHAT slice 2).

`ck_sales_opportunities_source` on `sales.opportunities` (created in `sales_0003_opportunities`) allowed 'portal' and
'crm' only. A salesperson who logs an opportunity in WhatsApp saves it through
`POST /api/v1/external/sales-opportunities` with source 'chat', so the check takes the third
value. Downgrade restores the two-value check; a row already saved as 'chat' would fail it, so
those rows are moved to 'portal' first (the nearest existing source: the salesperson's own
self-service channel).

Revision ID: stc_0002_opp_source_chat
Revises: lkp_0001_parser_lookup_lists
Create Date: 2026-10-25
"""
from __future__ import annotations

from alembic import op


revision = "stc_0002_opp_source_chat"
down_revision = "lkp_0001_parser_lookup_lists"
branch_labels = None
depends_on = None

_TABLE = "opportunities"
_SCHEMA = "sales"
_NAME = "ck_sales_opportunities_source"


def upgrade() -> None:
    op.drop_constraint(_NAME, _TABLE, schema=_SCHEMA, type_="check")
    op.create_check_constraint(_NAME, _TABLE, "source IN ('portal', 'crm', 'chat')", schema=_SCHEMA)


def downgrade() -> None:
    op.execute("UPDATE sales.opportunities SET source = 'portal' WHERE source = 'chat'")
    op.drop_constraint(_NAME, _TABLE, schema=_SCHEMA, type_="check")
    op.create_check_constraint(_NAME, _TABLE, "source IN ('portal', 'crm')", schema=_SCHEMA)
