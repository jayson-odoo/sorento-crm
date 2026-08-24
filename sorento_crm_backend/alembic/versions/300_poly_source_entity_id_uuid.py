"""Type the all-uuid polymorphic source_entity_id columns as uuid.

`conversation_sla_tracking.source_entity_id` and `user_downloads.source_entity_id`
are polymorphic (they point at whichever form/entity a tracker or download is
about), so they carry no FK - but every value they hold is a uuid, and now that
every domain table has a uuid `id` (see 298 + the schema-guard test) every value
they will EVER hold is a uuid. Typing them `uuid` makes Postgres reject a
`uuid = text` mismatch at write time instead of silently accepting it.

This is the column behind the original report: a hand-written
`conversation_sla_tracking.source_entity_id = (SELECT id FROM stock_inquiries …)`
raised `operator does not exist: character varying = uuid`. After this it is
`uuid = uuid`.

Every existing value was verified to be a valid uuid or NULL before the cast.

Revision ID: 300_poly_source_entity_id_uuid
Revises: 299_notif_dedup_key_split
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "300_poly_source_entity_id_uuid"
down_revision = "299_notif_dedup_key_split"
branch_labels = None
depends_on = None

_COLS = [
    ("conversation_sla_tracking", "source_entity_id"),
    ("user_downloads", "source_entity_id"),
]


def upgrade():
    for table, col in _COLS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE uuid USING {col}::uuid"
        )


def downgrade():
    for table, col in _COLS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(100) USING {col}::text"
        )
