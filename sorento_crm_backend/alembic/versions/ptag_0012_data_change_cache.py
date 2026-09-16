"""The price tag list's stored product-data-change cache (PLAN
price-tag-currency-token-extract-prompt.md section D).

Computing the diff per list row costs 16-414 ms of live resolve EACH - up to
50 x 60 ms on a full page. So the count is cached on the request, and the
list route refreshes it only for a row a cheap query says was touched since
its last check (``PriceTagRequestService.touched_request_ids``); every other
row is served from the stored count with no resolve at all.

``data_changed_tag_count`` defaults to 0 so an existing row (nothing has
checked it yet) shows no drift until the list route's next pass touches it.
``data_checked_at`` starts NULL, which the touched-row query reads the same
way it reads "never checked" - touched.

Revision ID: ptag_0012_data_change_cache
Revises: ptag_0011_line_promo
Create Date: 2026-09-16
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ptag_0012_data_change_cache"
down_revision = "ptag_0011_line_promo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_tag_requests",
        sa.Column(
            "data_changed_tag_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "price_tag_requests",
        sa.Column("data_checked_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("price_tag_requests", "data_checked_at")
    op.drop_column("price_tag_requests", "data_changed_tag_count")
