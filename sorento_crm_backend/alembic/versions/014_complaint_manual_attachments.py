"""Complaint manual attachments (pass-through migration)

Revision ID: 014_complaint_manual_attachments
Revises: 013_event_log_assigned_to_id
Create Date: 2026-01-25 00:00:00.000000

This is a pass-through migration to maintain the revision chain.
The complaint_manual_attachments table was created manually or the original migration was removed.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_complaint_manual_attachments'
down_revision = '013_event_log_assigned_to_id'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pass-through migration - table/columns already exist or were created manually
    # No operations needed
    pass


def downgrade() -> None:
    # Pass-through migration - no operations needed
    pass
