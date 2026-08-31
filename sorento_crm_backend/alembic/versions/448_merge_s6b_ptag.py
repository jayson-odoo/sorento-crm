"""Merge the s6b permission head with the price-tag chain.

PR #411 (s6b_reference_data_manage_perm, down s6b_record_action_entity_id) and PR #289
(447_merge_ptag_ac, which also descends from s6b_record_action_entity_id) both merged to
main, leaving two heads. Every deploy since 2d37e4402 failed on the single-head gate and
on `alembic upgrade head`. Empty merge revision, no schema change.

Revision ID: 448_merge_s6b_ptag
Revises: 447_merge_ptag_ac, s6b_reference_data_manage_perm
Create Date: 2026-08-31
"""
from __future__ import annotations

revision = "448_merge_s6b_ptag"
down_revision = ("447_merge_ptag_ac", "s6b_reference_data_manage_perm")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
