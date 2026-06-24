"""SLA extend-deadline: policy soft limits, tracker counters, user notify toggles.

Revision ID: 244_sla_extend_deadline
Revises: 243_sponsor_subject_lookup
Create Date: 2026-06-24

Adds the columns backing the "Extend resolution deadline" feature
(PLAN-sla-extend-deadline):

- sla_policies: three nullable soft-limit columns (null = no limit; breach is a
  warning only, never blocks).
- conversation_sla_tracking: denormalized extension counters (the event log is the
  immutable trail; these are fast-read for soft-limit checks + the row chip).
- users: per-channel opt-in for the deadline_extended notification (recipient is the
  next escalation tier). Email defaults on, WhatsApp off (mirrors the existing
  assignment/escalation toggle defaults).

Idempotent and reversible.
"""
from alembic import op
import sqlalchemy as sa


revision = "244_sla_extend_deadline"
down_revision = "243_sponsor_subject_lookup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sla_policies",
        sa.Column("max_extension_days_per_request", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sla_policies",
        sa.Column("max_extension_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sla_policies",
        sa.Column("max_extension_days_total", sa.Numeric(10, 2), nullable=True),
    )

    op.add_column(
        "conversation_sla_tracking",
        sa.Column(
            "extension_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "conversation_sla_tracking",
        sa.Column(
            "extension_days_total",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "notify_email_on_deadline_extended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "notify_whatsapp_on_deadline_extended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "notify_whatsapp_on_deadline_extended")
    op.drop_column("users", "notify_email_on_deadline_extended")
    op.drop_column("conversation_sla_tracking", "extension_days_total")
    op.drop_column("conversation_sla_tracking", "extension_count")
    op.drop_column("sla_policies", "max_extension_days_total")
    op.drop_column("sla_policies", "max_extension_count")
    op.drop_column("sla_policies", "max_extension_days_per_request")
