"""Ideation embed SSO config columns on respond_workspaces.

Adds the three DB-driven embed-connection fields (mirrors the existing
``ideation_shared_service_url`` / ``ideation_intake_api_key_ciphertext`` pattern) so
the Ideas iframe SSO handshake is configured entirely from the FE admin, never
``.env`` (AC-E-1/E-14):

- ``ideation_embed_connection_id`` VARCHAR(128) — plain connection id the
  shared-service registry looks up.
- ``ideation_embed_signing_secret_ciphertext`` TEXT — Fernet-encrypted signing
  secret the assertion is minted with (never returned plaintext).
- ``ideation_embed_fe_base_url`` VARCHAR(512) — the shared-service **FE root** the
  iframe ``iframe_url`` is built from (distinct from ``ideation_shared_service_url``,
  the backend base used for ``POST /embed/session`` — AC-E-3).

All nullable + additive; blank keeps the embed feature dormant (AC-E-13).
Idempotent (``ADD COLUMN IF NOT EXISTS`` / ``DROP COLUMN IF EXISTS``) and reversible.

Revision ID: 288_ideation_embed_config
Revises: 287_form_void
Create Date: 2026-07-20
"""
from alembic import op


revision = "288_ideation_embed_config"
down_revision = "287_form_void"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_embed_connection_id VARCHAR(128)"
    )
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_embed_signing_secret_ciphertext TEXT"
    )
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_embed_fe_base_url VARCHAR(512)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces DROP COLUMN IF EXISTS ideation_embed_fe_base_url"
    )
    op.execute(
        "ALTER TABLE respond_workspaces "
        "DROP COLUMN IF EXISTS ideation_embed_signing_secret_ciphertext"
    )
    op.execute(
        "ALTER TABLE respond_workspaces DROP COLUMN IF EXISTS ideation_embed_connection_id"
    )
