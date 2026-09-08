"""price_tag_requests.price_mode + price_tag_request_lines.remarks (D5/D6)

PLAN-price-tag-r7-request-ux, AC-S2-6.

`price_mode` (`list | selling`) replaces the old per-line `show_promo_price`
switch as a header-level control on the request; `selling` requires a
promotion (enforced in the service, not here). `remarks` is a free-text
note on a line.

Both columns are additive. `price_mode` is NOT NULL with a `'list'`
server_default, so every existing row backfills to `list` - the same
value a new row gets when the payload does not name one - without a
separate UPDATE pass: Postgres populates a NOT NULL column added with a
constant default in place, no table rewrite. `remarks` is nullable.

Revision ID: ptag_0005
Revises: 492_mcp_tool_chatbot_domain
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "ptag_0005"
down_revision = "492_mcp_tool_chatbot_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "price_mode",
            sa.String(16),
            nullable=False,
            server_default="list",
        ),
    )
    op.add_column(
        "price_tag_request_lines",
        sa.Column("remarks", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_tag_request_lines", "remarks")
    op.drop_column("price_tag_requests", "price_mode")
