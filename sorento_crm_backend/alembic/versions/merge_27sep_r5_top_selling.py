"""Merge main's two heads of 27 Sep (#1298, #1302) with the top selling lane (PR #1273).

Main carries two heads, `527_audit_logs_scrub_secrets` and
`spec_0003_rules_null_brand_pol`, both from `merge_27sep_three_heads`, the same parent
the top selling lane's chain starts from. Schema-free merge point, so the lane lands
with one head and no migration main already has is edited.

Revision ID: merge_27sep_r5_top_selling
Revises: 527_audit_logs_scrub_secrets, spec_0003_rules_null_brand_pol, chatbot_top_selling_vocab_r5
"""
from __future__ import annotations

revision = "merge_27sep_r5_top_selling"
down_revision = ("527_audit_logs_scrub_secrets", "spec_0003_rules_null_brand_pol", "chatbot_top_selling_vocab_r5")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
