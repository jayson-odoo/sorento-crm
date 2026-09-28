"""Merge the heads left on main by the 28 Sep migration batch.

Each PR in the batch (#1313, #1301, #1332, #1296, #1273, #1329) chained on
`merge_28sep_esc_fin`; after they landed main carried these heads.
Schema-free merge point.

Revision ID: merge_28sep_batch2
Revises: chatbot_known_brands, soatt_0001_so_line_attachments
"""
from __future__ import annotations

revision = "merge_28sep_batch2"
down_revision = ("chatbot_known_brands", "soatt_0001_so_line_attachments")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
