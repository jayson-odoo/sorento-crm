"""add trace_id correlation column to audit_logs (Sub-plan D Tier-2)

Revision ID: 254_audit_trace_id
Revises: 253_system_settings_singleton
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "254_audit_trace_id"
down_revision = "253_system_settings_singleton"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "audit_logs",
        sa.Column("trace_id", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_audit_logs_trace_id", "audit_logs", ["trace_id"])


def downgrade():
    op.drop_index("ix_audit_logs_trace_id", table_name="audit_logs")
    op.drop_column("audit_logs", "trace_id")
