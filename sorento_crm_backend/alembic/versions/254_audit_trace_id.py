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
    # Idempotent: this migration forked from 253 in parallel with 255/256, so on
    # some environments the column/index may already exist (e.g. added during dev
    # before the branch merge). Guard so `upgrade head` never fails on re-apply.
    bind = op.get_bind()
    insp = sa.inspect(bind)
    columns = {c["name"] for c in insp.get_columns("audit_logs")}
    if "trace_id" not in columns:
        op.add_column(
            "audit_logs",
            sa.Column("trace_id", sa.String(length=64), nullable=True),
        )
    indexes = {i["name"] for i in insp.get_indexes("audit_logs")}
    if "ix_audit_logs_trace_id" not in indexes:
        op.create_index("ix_audit_logs_trace_id", "audit_logs", ["trace_id"])


def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    indexes = {i["name"] for i in insp.get_indexes("audit_logs")}
    if "ix_audit_logs_trace_id" in indexes:
        op.drop_index("ix_audit_logs_trace_id", table_name="audit_logs")
    columns = {c["name"] for c in insp.get_columns("audit_logs")}
    if "trace_id" in columns:
        op.drop_column("audit_logs", "trace_id")
