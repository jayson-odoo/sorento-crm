"""Form handling-lock: tracker handler columns, user handling toggles, per-form flag.

Revision ID: 269_form_handling_lock
Revises: 268_variant_link_manual
Create Date: 2026-07-10

Backs the "I'm handling this" handling-lock (PLAN-form-handling-lock):

- conversation_sla_tracking: ``handled_by_id`` (the active handler lock; NULL =
  unclaimed) + ``handled_at`` (when it was claimed). ``handled_by_id`` is FK
  users.id ON DELETE SET NULL and indexed for the CTA-guard lookup.
- users: per-event channel opt-ins for the handling notification
  (``notify_email_on_handling`` default on, ``notify_whatsapp_on_handling`` off —
  mirrors the assignment/escalation toggle defaults).
- system_settings: ``handling_lock_enabled_types`` — CSV of the source_entity_types
  the lock is enabled for. Empty (default) = off for every form = today's behavior.

Idempotent and reversible. No backfill (NULL handled_by_id = unclaimed is correct
for existing rows).
"""
from alembic import op
import sqlalchemy as sa


revision = "269_form_handling_lock"
down_revision = "268_variant_link_manual"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_sla_tracking",
        sa.Column(
            "handled_by_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "conversation_sla_tracking",
        sa.Column("handled_at", sa.DateTime(timezone=False), nullable=True),
    )
    op.create_index(
        "ix_conversation_sla_tracking_handled_by_id",
        "conversation_sla_tracking",
        ["handled_by_id"],
    )

    op.add_column(
        "users",
        sa.Column(
            "notify_email_on_handling",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "notify_whatsapp_on_handling",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.add_column(
        "system_settings",
        sa.Column(
            "handling_lock_enabled_types",
            sa.Text(),
            nullable=True,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("system_settings", "handling_lock_enabled_types")
    op.drop_column("users", "notify_whatsapp_on_handling")
    op.drop_column("users", "notify_email_on_handling")
    op.drop_index(
        "ix_conversation_sla_tracking_handled_by_id",
        table_name="conversation_sla_tracking",
    )
    op.drop_column("conversation_sla_tracking", "handled_at")
    op.drop_column("conversation_sla_tracking", "handled_by_id")
