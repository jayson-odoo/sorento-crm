"""Per-contact outbound kill switch: respond_contacts.outbound_enabled.

Replaces the RESPOND_SEND_ALLOWLIST env-var stopgap with a real, per-contact
column that operations can flip without a redeploy. NOT NULL DEFAULT true, so
every existing contact stays enabled on upgrade - the deploy changes no
behaviour for anyone, and a container that predates the column still inserts
successfully.

Idempotent (IF NOT EXISTS): the shared dev database gets this DDL applied by
hand, and a re-run must never reset a deliberately muted contact.

Revision ID: 325_respond_contact_outbound
Revises: 324_ticket_source_message_restore
Create Date: 2026-08-14
"""
from alembic import op
from sqlalchemy import text


revision = "325_respond_contact_outbound"
down_revision = "324_ticket_source_message_restore"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        text(
            "ALTER TABLE respond_contacts "
            "ADD COLUMN IF NOT EXISTS outbound_enabled BOOLEAN NOT NULL DEFAULT TRUE"
        )
    )


def downgrade() -> None:
    op.execute(
        text("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS outbound_enabled")
    )
