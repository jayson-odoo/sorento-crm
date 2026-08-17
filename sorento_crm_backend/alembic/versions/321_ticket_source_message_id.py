"""Conversation intervention tickets: per-enquiry identity replaces the contact singleton.

A conversation SLA row stops meaning "the open conversation with this contact" and
starts meaning "this enquiry". Three moves, in this order:

1. add `source_message_id` (Text, nullable) - the message that asked for a human;
2. backfill it from `message_id` on conversation-scope rows (idempotent: set where
   it differs, so a re-run repairs an earlier partial run);
3. swap migration 180's one-open-row-per-contact unique index for a unique index on
   `source_message_id` over OPEN conversation-scope rows only.

Form-SLA rows (source_entity_type in the form types) are untouched by every step:
they never carry a trigger message and they sit outside both index predicates.

Revision ID: 321_ticket_source_message_id
Revises: cac36dbd46ab
Create Date: 2026-08-12
"""
from alembic import op
from sqlalchemy import text


revision = "321_ticket_source_message_id"
down_revision = "cac36dbd46ab"
branch_labels = None
depends_on = None

OLD_INDEX = "uq_conversation_sla_tracking_active_conversation_per_contact"
NEW_INDEX = "uq_conversation_sla_tracking_open_source_message"

# The conversation family, matching migration 180's predicate (form rows excluded).
CONVERSATION_SCOPE = "(source_entity_type IS NULL OR source_entity_type = 'conversation')"


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE conversation_sla_tracking "
            "ADD COLUMN IF NOT EXISTS source_message_id TEXT"
        )
    )

    # Backfill: the trigger message n8n already sends as message_id becomes the
    # ticket's identity, so today's open rows keep their idempotency across the
    # deploy. "Set where it differs" rather than "where NULL" so a re-run also
    # repairs a row an earlier run wrote wrongly.
    op.execute(
        text(
            f"""
            UPDATE conversation_sla_tracking
               SET source_message_id = message_id::text
             WHERE message_id IS NOT NULL
               AND {CONVERSATION_SCOPE}
               AND source_message_id IS DISTINCT FROM message_id::text
            """
        )
    )

    # The unique index below would abort the whole migration if the backfill ever
    # produced two OPEN rows sharing a message id (an overwrite-in-place row pair,
    # or hand-edited data). Keep the newest row's identity and blank the rest:
    # message_id itself is untouched, so nothing real is lost, and the migration
    # cannot fail on live data.
    op.execute(
        text(
            f"""
            UPDATE conversation_sla_tracking
               SET source_message_id = NULL
             WHERE id IN (
                 SELECT id FROM (
                     SELECT id,
                            row_number() OVER (
                                PARTITION BY source_message_id
                                ORDER BY created_at DESC, id DESC
                            ) AS rn
                       FROM conversation_sla_tracking
                      WHERE source_message_id IS NOT NULL
                        AND is_resolved = false
                        AND {CONVERSATION_SCOPE}
                 ) ranked
                 WHERE ranked.rn > 1
             )
            """
        )
    )

    # Multi-open per contact is now the point of the feature.
    op.execute(text(f"DROP INDEX IF EXISTS {OLD_INDEX}"))

    op.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX}
            ON conversation_sla_tracking (source_message_id)
            WHERE source_message_id IS NOT NULL
              AND is_resolved = false
              AND {CONVERSATION_SCOPE}
            """
        )
    )


def downgrade() -> None:
    op.execute(text(f"DROP INDEX IF EXISTS {NEW_INDEX}"))

    # Restoring the contact singleton means at most one open row per contact again.
    # Any extra open tickets a contact accumulated while multi-open was live are
    # resolved (not deleted) so the unique index can be rebuilt without data loss.
    op.execute(
        text(
            f"""
            UPDATE conversation_sla_tracking
               SET is_resolved = true,
                   resolved_at = COALESCE(resolved_at, now()),
                   resolved_by = COALESCE(resolved_by, 'downgrade:321')
             WHERE id IN (
                 SELECT id FROM (
                     SELECT id,
                            row_number() OVER (
                                PARTITION BY respond_contact_id
                                ORDER BY created_at DESC, id DESC
                            ) AS rn
                       FROM conversation_sla_tracking
                      WHERE respond_contact_id IS NOT NULL
                        AND is_resolved = false
                        AND {CONVERSATION_SCOPE}
                 ) ranked
                 WHERE ranked.rn > 1
             )
            """
        )
    )
    op.execute(
        text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {OLD_INDEX}
            ON conversation_sla_tracking (respond_contact_id)
            WHERE respond_contact_id IS NOT NULL
              AND is_resolved = false
              AND {CONVERSATION_SCOPE}
            """
        )
    )
    op.execute(
        text(
            "ALTER TABLE conversation_sla_tracking DROP COLUMN IF EXISTS source_message_id"
        )
    )
