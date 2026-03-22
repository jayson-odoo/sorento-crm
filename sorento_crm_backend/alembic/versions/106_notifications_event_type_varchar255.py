"""Widen notifications.event_type for workflow transition idempotency keys.

Revision ID: 106_notifications_event_type_varchar255
Revises: 105_workflow_forms
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "106_notifications_event_type_varchar255"
down_revision = "105_workflow_forms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "notifications",
        "event_type",
        existing_type=sa.String(80),
        type_=sa.String(255),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "notifications",
        "event_type",
        existing_type=sa.String(255),
        type_=sa.String(80),
        existing_nullable=True,
    )
