"""TAG-UNION: respond_contacts.tag_settings_snapshot (JSONB, NULL = never seeded).

Plan documentation/plans/contacts/PLAN-tag-union-08nov.md. Additive and idempotent (the shared dev
database converges through create_all). Nothing is backfilled here: the snapshot is seeded by
`scripts/recompute_contact_tag_union.py` (owner runs it) or on the contact's next tag change.

Revision ID: tagu_0001_tag_snapshot
Revises: qcert_0001_quote_certificates
"""
from __future__ import annotations

from alembic import op

revision = "tagu_0001_tag_snapshot"
down_revision = "qcert_0001_quote_certificates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS tag_settings_snapshot JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS tag_settings_snapshot")
