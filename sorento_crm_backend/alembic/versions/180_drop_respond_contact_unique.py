"""Drop the global unique on conversation_sla_tracking.respond_contact_id.

The legacy constraint forced one tracker per contact, which is correct for the
original conversation SLA flow but blocks the multi-stage / multi-form trackers
introduced for form SLA. Conversation-tracker uniqueness is enforced at the
service layer (ConversationSLATrackingService.create_tracking) via the active-
tracker conflict check, so dropping the DB constraint does not relax the
conversation behaviour.

Revision ID: 180_drop_respond_contact_unique
Revises: 179_seed_form_sla_overdue_scan
Create Date: 2026-05-09
"""
from alembic import op
from sqlalchemy import text


revision = "180_drop_respond_contact_unique"
down_revision = "179_seed_form_sla_overdue_scan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE conversation_sla_tracking "
            "DROP CONSTRAINT IF EXISTS respond_contact_id_unique"
        )
    )
    op.execute(
        text(
            "DROP INDEX IF EXISTS uq_conversation_sla_tracking_respond_contact_id"
        )
    )
    # Partial unique: only enforce at most one active conversation-only tracker per contact.
    # Form trackers (source_entity_type IN form types) and resolved trackers are unrestricted.
    op.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sla_tracking_active_conversation_per_contact
            ON conversation_sla_tracking (respond_contact_id)
            WHERE respond_contact_id IS NOT NULL
              AND is_resolved = false
              AND (source_entity_type IS NULL OR source_entity_type = 'conversation')
            """
        )
    )


def downgrade() -> None:
    op.execute(
        text(
            "DROP INDEX IF EXISTS uq_conversation_sla_tracking_active_conversation_per_contact"
        )
    )
    op.execute(
        text(
            "ALTER TABLE conversation_sla_tracking "
            "ADD CONSTRAINT respond_contact_id_unique UNIQUE (respond_contact_id)"
        )
    )
