"""Restore ticket identity that migration 321 over-deduped across contacts.

Migration 321 backfilled `source_message_id` from `message_id` and then had to
guarantee its own unique index on `source_message_id` ALONE, so it blanked every
duplicate but the newest - partitioning by the message id with no contact scope.
Migration 323 then corrected the identity to the pair (contact, message), but a
row 321 had already cleared stayed cleared: two DIFFERENT contacts whose trigger
messages happened to share an id lost their idempotency permanently, and the
next n8n retry of either would open a duplicate ticket instead of returning the
existing one.

Restore it where the pair now allows it:

- only OPEN conversation-scope rows (form-SLA rows never carried a trigger
  message and sit outside both index predicates);
- only where `source_message_id` is NULL and `message_id` survives (321 never
  touched `message_id`, which is why nothing was actually lost);
- never where another OPEN row for the SAME contact already holds that id, and
  never more than one candidate per (contact, message) - so the 323 index can
  not be violated by this backfill.

Same-contact duplicates stay blanked: those are the collisions the identity
genuinely forbids.

Idempotent by construction (it only writes NULLs), so it is safe on a database
where 321/322/323 were applied by hand as well as on a fresh
`alembic upgrade head`.

Revision ID: 324_ticket_source_message_restore
Revises: 323_ticket_source_message_contact_scope
Create Date: 2026-08-13
"""
from alembic import op
from sqlalchemy import text


revision = "324_ticket_source_message_restore"
down_revision = "323_ticket_source_message_contact_scope"
branch_labels = None
depends_on = None

# The conversation family, matching migrations 180/321/323.
CONVERSATION_SCOPE = "(source_entity_type IS NULL OR source_entity_type = 'conversation')"


def upgrade() -> None:
    op.execute(
        text(
            f"""
            WITH candidate AS (
                SELECT id,
                       respond_contact_id,
                       message_id::text AS restored_id,
                       row_number() OVER (
                           PARTITION BY respond_contact_id, message_id::text
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                  FROM conversation_sla_tracking
                 WHERE source_message_id IS NULL
                   AND message_id IS NOT NULL
                   AND is_resolved = false
                   AND {CONVERSATION_SCOPE}
            )
            UPDATE conversation_sla_tracking AS t
               SET source_message_id = c.restored_id
              FROM candidate AS c
             WHERE t.id = c.id
               AND c.rn = 1
               AND NOT EXISTS (
                   SELECT 1
                     FROM conversation_sla_tracking AS other
                    WHERE other.id <> c.id
                      AND other.respond_contact_id IS NOT DISTINCT FROM c.respond_contact_id
                      AND other.source_message_id = c.restored_id
                      AND other.is_resolved = false
                      AND (other.source_entity_type IS NULL
                           OR other.source_entity_type = 'conversation')
               )
            """
        )
    )


def downgrade() -> None:
    # Nothing to undo: the restored value is exactly `message_id`, which was
    # never removed, and blanking it again would only re-create the defect.
    pass
