"""ESCALATION-CONTROL - per access type / per contact escalation switch.

`contact_access_types.escalation_allowed` BOOLEAN NOT NULL DEFAULT true, seeded false for
the "Sorento Dealer" type (owner, 30 Sep 2026: a dealer is never offered and cannot force
an escalation; their contact point is the salesperson). The type is admin-created, not
migration-seeded, so it is matched by name. `respond_contacts.escalation_allowed` BOOLEAN
NULL is the contact's own override (NULL = inherit). Additive and re-runnable.

Revision ID: esc1_0001_escalation_allowed
Revises: oihr_0004_wide_line_table
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "esc1_0001_escalation_allowed"
down_revision = "oihr_0004_wide_line_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE contact_access_types ADD COLUMN IF NOT EXISTS escalation_allowed "
            "BOOLEAN NOT NULL DEFAULT true"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE contact_access_types SET escalation_allowed = false "
            "WHERE lower(trim(name)) = 'sorento dealer'"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS escalation_allowed BOOLEAN NULL"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS escalation_allowed"))
    bind.execute(sa.text("ALTER TABLE contact_access_types DROP COLUMN IF EXISTS escalation_allowed"))
