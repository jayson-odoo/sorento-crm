"""Merge the two heads origin/main carries at 9751e55d with the sales S1 + S2 chain.

origin/main at 9751e55d has two heads, both on `merge_27sep_three_heads`
(`527_audit_logs_scrub_secrets`, `spec_0003_rules_null_brand_pol`); the sales lane adds a
third (`sales_0005_opp_line_price`). No schema change.

Revision ID: sales_0005m_merge_main_heads
Revises: sales_0005_opp_line_price, 527_audit_logs_scrub_secrets, spec_0003_rules_null_brand_pol
Create Date: 2026-09-27
"""

revision = "sales_0005m_merge_main_heads"
down_revision = (
    "sales_0005_opp_line_price",
    "527_audit_logs_scrub_secrets",
    "spec_0003_rules_null_brand_pol",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
