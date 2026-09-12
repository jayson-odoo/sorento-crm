"""`companies` gains `so_feed_live` (PLAN company-so-feed-flag).

Mocha has no sales orders in the CRM yet - its AutoCount SO feed is not
connected - so every Mocha stock row printed `Outstanding: 0`, which reads as
"nothing on order" when the truth is "we do not know". One boolean on
`companies`, switched from the Companies admin page: off withholds
`open_so_qty` / `sellable` from that company's stock rows; no deploy needed
when the feed lands.

Mocha is flipped off here, by code. Sorento (and every other company) stays
true so nothing changes for it.

Revision ID: 495_company_so_feed_live
Revises: 494_from_so_external_link
"""
import sqlalchemy as sa
from alembic import op

revision = "495_company_so_feed_live"
down_revision = "494_from_so_external_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("so_feed_live", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE companies SET so_feed_live = false WHERE code = 'MOCHA'")


def downgrade() -> None:
    op.drop_column("companies", "so_feed_live")
