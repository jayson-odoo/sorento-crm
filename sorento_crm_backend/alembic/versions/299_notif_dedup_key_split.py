"""Split notifications.source_entity_id into a uuid entity ref + a text dedup_key.

`notifications.source_entity_id` was overloaded: for an entity notification it
held the entity's uuid, but for batched / periodic notifications it held a
synthetic idempotency key with no entity behind it  - 
`alert:integration_spike:2026-07-13T08:24:10`, `digest:2026-07-13`,
`{type}_{batch}`, `{uuid}:{date}`. That overload is the only reason the column
had to be `varchar`, and it blocked typing it `uuid` (which would let Postgres
reject a `uuid = text` mismatch).

Give the dedup role its own `dedup_key` column and let `source_entity_id` become
a nullable uuid. The idempotency contract is preserved exactly: the unique index
and the app-level dedup lookup move from `source_entity_id` onto `dedup_key`,
and `dedup_key` is backfilled from the old `source_entity_id` value - so every
row keeps the exact key it de-duplicated on before.

Revision ID: 299_notif_dedup_key_split
Revises: 298_market_segments_uuid_id
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "299_notif_dedup_key_split"
down_revision = "298_market_segments_uuid_id"
branch_labels = None
depends_on = None

_UUID_RE = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_OLD_UQ = "uq_notification_user_source_event"
_NEW_UQ = "uq_notification_user_dedup_event"


def upgrade():
    # 1. New column, carrying the dedup role.
    op.execute("ALTER TABLE notifications ADD COLUMN dedup_key VARCHAR(255)")
    # 2. Every row keeps the exact value it de-duplicated on.
    op.execute("UPDATE notifications SET dedup_key = source_entity_id")
    # 3. Move the DB-enforced idempotency onto dedup_key BEFORE narrowing
    #    source_entity_id (the old constraint references the column we're
    #    retyping). It is a UNIQUE CONSTRAINT (the model declares it via
    #    UniqueConstraint), so drop the constraint, not a bare index.
    op.execute(f"ALTER TABLE notifications DROP CONSTRAINT {_OLD_UQ}")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT {_NEW_UQ} "
        "UNIQUE (user_id, source_entity_type, dedup_key, event_type)"
    )
    op.execute("CREATE INDEX ix_notifications_dedup_key ON notifications (dedup_key)")
    # 4. source_entity_id now means only "the entity this is about". Anything that
    #    is not a bare uuid was a synthetic key - it now lives in dedup_key, so
    #    null it here.
    op.execute(
        f"UPDATE notifications SET source_entity_id = NULL "
        f"WHERE source_entity_id IS NOT NULL AND source_entity_id !~ '{_UUID_RE}'"
    )
    # 5. Retype to uuid - every surviving value is a valid uuid or NULL.
    op.execute(
        "ALTER TABLE notifications "
        "ALTER COLUMN source_entity_id TYPE uuid USING source_entity_id::uuid"
    )


def downgrade():
    op.execute(
        "ALTER TABLE notifications "
        "ALTER COLUMN source_entity_id TYPE VARCHAR(255) USING source_entity_id::text"
    )
    # Restore the synthetic keys back onto source_entity_id where it was nulled.
    op.execute(
        "UPDATE notifications SET source_entity_id = dedup_key "
        "WHERE source_entity_id IS NULL AND dedup_key IS NOT NULL"
    )
    op.execute("DROP INDEX IF EXISTS ix_notifications_dedup_key")
    op.execute(f"ALTER TABLE notifications DROP CONSTRAINT {_NEW_UQ}")
    op.execute(
        f"ALTER TABLE notifications ADD CONSTRAINT {_OLD_UQ} "
        "UNIQUE (user_id, source_entity_type, source_entity_id, event_type)"
    )
    op.execute("ALTER TABLE notifications DROP COLUMN dedup_key")
