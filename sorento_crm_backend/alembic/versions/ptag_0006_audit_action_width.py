"""audit_logs.action: widen 20 -> 40 chars (D-P6 portal_edit_after_submit)

PLAN-portal-price-tag-journey-r8, S8/AC-B1.

The column has only ever carried short verbs (``INSERT`` / ``UPDATE`` /
``DELETE`` / ``created`` / ``updated``) - every ``log_audit`` caller in the
codebase before this one used one of those. The post-submit portal edit
gate needs a self-describing action name, ``portal_edit_after_submit``
(24 chars), to tell it apart from an ordinary draft save at a glance in the
audit log; 20 chars has no room for that. Purely additive - narrower
existing values are untouched.

Revision ID: ptag_0006
Revises: 512_hidden_by_default_col
Create Date: 2026-09-12
"""
import sqlalchemy as sa
from alembic import op

revision = "ptag_0006"
down_revision = "512_hidden_by_default_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "audit_logs",
        "action",
        type_=sa.String(40),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "audit_logs",
        "action",
        type_=sa.String(20),
        existing_type=sa.String(40),
        existing_nullable=False,
    )
