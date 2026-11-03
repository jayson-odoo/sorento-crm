"""Join the heads left on main by the #2102 and #2104 merges.

#2102 landed `qiv_0001_issue_views` and #2104 landed
`bnsp_0001_brand_no_selling_price`, both hung off
`qcp_0001_cover_page_fields`, so main carried two heads. Schema-free
merge point.

Revision ID: join_0003_qiv_bnsp
Revises: qiv_0001_issue_views, bnsp_0001_brand_no_selling_price
"""
from __future__ import annotations

revision = "join_0003_qiv_bnsp"
down_revision = ("qiv_0001_issue_views", "bnsp_0001_brand_no_selling_price")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
