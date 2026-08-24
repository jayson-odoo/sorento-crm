"""Widen audit_logs.entity_id from uuid to text.

`audit_logs` is polymorphic: `audit_service._entity_id_str` stores whatever the
audited entity's primary key is, and not every PK is a UUID - `MarketSegment`
is keyed by a `code` such as 'MSEG-A'.

Typing the column `uuid` therefore rejects those inserts. Because audit writes
are best-effort (they must never fail the user's operation), the rejection was
swallowed and the audit row simply never appeared. Evidence on the live dataset:
1,659,463 audit rows total, and 0 for any segment entity.

Widening to text lets every entity be audited regardless of PK type. UUID-keyed
entities keep storing the same 36-char string, so existing rows and queries are
unaffected - Postgres casts uuid to text losslessly.

Revision ID: 297_audit_entity_id_text
Revises: 296_drop_commercial_modules
"""
from alembic import op

revision = "297_audit_entity_id_text"
down_revision = "296_drop_commercial_modules"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE audit_logs "
        "ALTER COLUMN entity_id TYPE VARCHAR(100) USING entity_id::text"
    )


def downgrade():
    """Narrow back to uuid.

    Only safe while every stored entity_id is a valid UUID; any non-UUID row
    written after the upgrade will make this fail, which is the intended
    protection rather than silent data loss.
    """
    op.execute(
        "ALTER TABLE audit_logs "
        "ALTER COLUMN entity_id TYPE uuid USING entity_id::uuid"
    )
