"""form-banner person links: escalated-from + PR rejected-by attribution columns

Two nullable FK columns so form-detail banners can show WHO did the thing and
link to their wa.me:

1. conversation_sla_event_log.from_assigned_to_id — the PRIOR assignee snapshotted
   at escalation time (BEFORE the new assignee overwrites assigned_to_id). The
   escalation banner reads the latest escalation event's from_assigned_to_id.
2. purchase_requests.rejected_by_id — the CRM user who rejected the PR (dedicated
   column; approved_by holds only a display-name string). NULL for external-email
   approvers and legacy rejections (banner falls back to plain text).

Both FK -> users.id, ON DELETE SET NULL, nullable. Idempotent (IF NOT EXISTS).

Revision ID: 272_banner_person_link_fields
Revises: 271_audit_action_allow_import
"""
from alembic import op


revision = "272_banner_person_link_fields"
down_revision = "271_audit_action_allow_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE conversation_sla_event_log "
        "ADD COLUMN IF NOT EXISTS from_assigned_to_id VARCHAR"
    )
    op.execute(
        "ALTER TABLE conversation_sla_event_log "
        "DROP CONSTRAINT IF EXISTS conversation_sla_event_log_from_assigned_to_id_fkey"
    )
    op.execute(
        "ALTER TABLE conversation_sla_event_log "
        "ADD CONSTRAINT conversation_sla_event_log_from_assigned_to_id_fkey "
        "FOREIGN KEY (from_assigned_to_id) REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_conversation_sla_event_log_from_assigned_to_id "
        "ON conversation_sla_event_log (from_assigned_to_id)"
    )

    op.execute(
        "ALTER TABLE purchase_requests "
        "ADD COLUMN IF NOT EXISTS rejected_by_id VARCHAR"
    )
    op.execute(
        "ALTER TABLE purchase_requests "
        "DROP CONSTRAINT IF EXISTS purchase_requests_rejected_by_id_fkey"
    )
    op.execute(
        "ALTER TABLE purchase_requests "
        "ADD CONSTRAINT purchase_requests_rejected_by_id_fkey "
        "FOREIGN KEY (rejected_by_id) REFERENCES users(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE purchase_requests "
        "DROP CONSTRAINT IF EXISTS purchase_requests_rejected_by_id_fkey"
    )
    op.execute("ALTER TABLE purchase_requests DROP COLUMN IF EXISTS rejected_by_id")
    op.execute(
        "DROP INDEX IF EXISTS ix_conversation_sla_event_log_from_assigned_to_id"
    )
    op.execute(
        "ALTER TABLE conversation_sla_event_log "
        "DROP CONSTRAINT IF EXISTS conversation_sla_event_log_from_assigned_to_id_fkey"
    )
    op.execute(
        "ALTER TABLE conversation_sla_event_log DROP COLUMN IF EXISTS from_assigned_to_id"
    )
