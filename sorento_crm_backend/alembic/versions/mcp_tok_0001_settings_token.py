"""MCP bearer token moves from env to `system_settings` (MCP-TOKEN-UI).

Five additive columns, all empty: no token means the backend sends no header and the MCP
server lets a headerless call through until Enforce is switched on, so a release with this
migration changes nothing for the chatbot. No permission seed: the screen reuses
`user_management.settings.secrets` (rts_0001_runtime_settings).

Idempotent: `create_all` may already have added the columns on a bootstrapped database.

Revision ID: mcp_tok_0001_settings_token
Revises: sfq_0001_sample_request_source
"""
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


def upgrade() -> None:
    for name, ddl in _COLUMNS:
        op.execute(f"ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS {name} {ddl}")


def downgrade() -> None:
    for name, _ddl in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE system_settings DROP COLUMN IF EXISTS {name}")
