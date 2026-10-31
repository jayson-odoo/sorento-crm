"""MCP bearer token moves from env to `system_settings` (MCP-TOKEN-UI).

Five additive columns, plus a first random token on the existing settings row (Enforce stays
off). The token is what keeps the staff AI assistant whole on release: the MCP server honours its
`X-MCP-Scope: staff` opt-out only on a call that carries a valid bearer (SEC-MCP-AUTH), so a
release with NO token would leave its company-scoped tools answering `scope_required` until an
admin clicked Generate. n8n, which sends no header, keeps working because Enforce is off; the
admin clicks Rotate on Settings > Integrations to get a value to paste into n8n (the seeded one
then stays valid for the grace window). No permission seed: the screen reuses
`user_management.settings.secrets` (rts_0001_runtime_settings).

Idempotent: `create_all` may already have added the columns on a bootstrapped database.

Revision ID: mcp_tok_0001_settings_token
Revises: sfq_0001_sample_request_source
"""
import secrets
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "mcp_tok_0001_settings_token"
down_revision = "sfq_0001_sample_request_source"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("mcp_auth_token_ciphertext", "TEXT"),
    ("mcp_auth_token_rotated_at", "TIMESTAMPTZ"),
    ("mcp_auth_previous_token_ciphertext", "TEXT"),
    ("mcp_auth_previous_expires_at", "TIMESTAMPTZ"),
    ("mcp_auth_enforce", "BOOLEAN NOT NULL DEFAULT false"),
)


def _seed_first_token(conn) -> None:
    """A first token where none is stored; never overwrites one. The value is not kept anywhere
    but the ciphertext: nobody needs it, the admin rotates to get one to paste."""
    from app.utils.field_encryption import encrypt_secret

    conn.execute(
        sa.text(
            "UPDATE system_settings SET mcp_auth_token_ciphertext = :c, mcp_auth_token_rotated_at = :now "
            "WHERE mcp_auth_token_ciphertext IS NULL"
        ),
        {"c": encrypt_secret(secrets.token_urlsafe(32)), "now": datetime.now(timezone.utc)},
    )


def upgrade() -> None:
    for name, ddl in _COLUMNS:
        op.execute(f"ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS {name} {ddl}")
    _seed_first_token(op.get_bind())


def downgrade() -> None:
    for name, _ddl in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE system_settings DROP COLUMN IF EXISTS {name}")
