"""ESCALATION-CONTROL - per access type / per contact escalation switch.

`contact_access_types.escalation_allowed` BOOLEAN NOT NULL DEFAULT true, seeded false for
EVERY dealer type (owner, 30 Sep 2026: "all dealer block escalation by default"; their
contact point is the salesperson). The table carries no kind or tier column, so a dealer
type is one whose name ends in the word "Dealer", any case (`DEALER_NAME_SQL`). `respond_contacts.escalation_allowed` BOOLEAN
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

#: Every dealer type: a name whose last word is "Dealer", any case ("Dealer", "Sorento
#: Dealer", "Cabana Dealer", "Mocha Dealer", "NL Dealer"). `contact_access_types` has no
#: kind or tier column (`app/models/access.py::ContactAccessType`); the chatbot's own tier
#: reading parses the name too (`lanes/business/tier_gate.py::parse_level`).
DEALER_NAME_SQL = "name ~* '(^|\\s)dealer\\s*$'"


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
            f"WHERE {DEALER_NAME_SQL}"
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
