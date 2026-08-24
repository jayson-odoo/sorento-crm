"""Bookmarkable portal links + device trust.

- `respond_contacts.portal_slug` - stable per-contact slug for the
  bookmarkable portal URL `/portal/c/{slug}`. Lazily minted on the next
  portal-link request, hence nullable with a partial unique index.
- `portal_tokens.is_impersonation` - admin "view as contact" tokens are
  excluded from the sliding 30-day TTL and never persist on the admin's
  machine. Backfilled from `contact_impersonation_sessions`.
- `respond_workspaces.whatsapp_number` - the business WhatsApp number used
  for the verify page's wa.me click-to-chat escape hatch (1 workspace =
  1 WhatsApp channel). Env `PORTAL_WHATSAPP_NUMBER` acts as fallback.

Idempotent: guards each DDL with IF NOT EXISTS / column checks so re-runs
and pre-provisioned environments are no-ops.

Revision ID: 224_portal_slug_device_trust
Revises: 223_stock_list_allow_xlsm
Create Date: 2026-06-04
"""
from __future__ import annotations

from alembic import op


revision = "224_portal_slug_device_trust"
down_revision = "223_stock_list_allow_xlsm"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS portal_slug VARCHAR(16)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_respond_contacts_portal_slug
        ON respond_contacts (portal_slug)
        WHERE portal_slug IS NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE portal_tokens
        ADD COLUMN IF NOT EXISTS is_impersonation BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    # Backfill: any token ever referenced by an impersonation session is an
    # impersonation token (JOIN-based "set to correct value where mismatch"  - 
    # safe to re-run).
    op.execute(
        """
        UPDATE portal_tokens pt
        SET is_impersonation = TRUE
        FROM contact_impersonation_sessions cis
        WHERE cis.portal_token_id = pt.id
          AND pt.is_impersonation IS DISTINCT FROM TRUE
        """
    )
    op.execute(
        """
        ALTER TABLE respond_workspaces
        ADD COLUMN IF NOT EXISTS whatsapp_number VARCHAR(32)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_respond_contacts_portal_slug")
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS portal_slug")
    op.execute("ALTER TABLE portal_tokens DROP COLUMN IF EXISTS is_impersonation")
    op.execute("ALTER TABLE respond_workspaces DROP COLUMN IF EXISTS whatsapp_number")
