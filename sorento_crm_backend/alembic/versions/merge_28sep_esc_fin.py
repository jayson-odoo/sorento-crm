"""Merge the two heads left on main by the 28 Sep merges (#1324, #1321).

Both branch from `fin_0001_billing_documents`. Schema-free merge point.

Revision ID: merge_28sep_esc_fin
Revises: chatbot_esc_confirm_1323, fin_0002_billing_demand_class
"""
from __future__ import annotations

revision = "merge_28sep_esc_fin"
down_revision = ("chatbot_esc_confirm_1323", "fin_0002_billing_demand_class")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
