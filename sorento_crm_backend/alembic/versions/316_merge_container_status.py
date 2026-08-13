"""Merge the container-status chain with main.

Both branches forked from `310_form_sla_skip_stage` and numbered their own
311-313, so merging main leaves two heads and `alembic upgrade head` refuses to
run ("Multiple heads are present"). That fails the deploy, not just CI.

No DDL: this exists only to rejoin the graph.

Revision ID: 316_merge_container_status
Revises: 313_purchase_request_pic, 315_contact_attachment_types
"""
from __future__ import annotations

revision = "316_merge_container_status"
down_revision = ("313_purchase_request_pic", "315_contact_attachment_types")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
