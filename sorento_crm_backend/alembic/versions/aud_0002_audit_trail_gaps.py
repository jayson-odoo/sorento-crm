"""Audit trail gaps: the records a failed audit capture left without their trail.

Owner ruling 28 Sep 2026 19:1x MYT, verbatim: "hmm if writing to audit fails, the save
shouldn't fail, right? for business flow shouldn't fail if the audit writing fail?" then "go"
(documentation/plans/audit/PLAN-audit-standard-26sep.md "Best-effort capture"). The capture
hooks write one row here per affected record when their savepoint fails; the error is on the
matching `integration_log` row (channel `audit`). A new, empty table: no lock on any
existing one.

Revision ID: aud_0002_audit_trail_gaps
Revises: aud_0001_audit_standard_s0
Create Date: 2026-09-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "aud_0002_audit_trail_gaps"
down_revision = "aud_0001_audit_standard_s0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_trail_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("integration_log_id", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=False), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("backfilled_at", sa.DateTime(timezone=False), nullable=True),
        if_not_exists=True,
    )
    op.create_index("ix_audit_trail_gaps_entity", "audit_trail_gaps", ["entity_type", "entity_id"], if_not_exists=True)
    op.create_index("ix_audit_trail_gaps_occurred_at", "audit_trail_gaps", ["occurred_at"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("ix_audit_trail_gaps_occurred_at", table_name="audit_trail_gaps", if_exists=True)
    op.drop_index("ix_audit_trail_gaps_entity", table_name="audit_trail_gaps", if_exists=True)
    op.drop_table("audit_trail_gaps", if_exists=True)
