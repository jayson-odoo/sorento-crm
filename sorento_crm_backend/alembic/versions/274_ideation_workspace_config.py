"""add ideation shared-service url + intake api key to respond_workspaces

Moves the ideation connection config OFF `.env`/app.config and ONTO the
workspace row, mirroring the respond.io `api_key_ciphertext` encrypted-key
pattern. Each workspace now carries:

  - ideation_shared_service_url  - the shared-service base URL (plain text)
  - ideation_intake_api_key_ciphertext - the intake API key, Fernet-encrypted
    via app/utils/field_encryption (same scheme as api_key_ciphertext)

(`ideation_product_id` already exists - migration 273.) The ideate brain path
now reads all three from the DEFAULT workspace and only falls back to
app.config settings when the workspace fields are blank (keeps legacy .env
installs working). NULL/blank keeps ideation fail-closed for that workspace.

Idempotent: ADD/DROP COLUMN ... IF (NOT) EXISTS so a re-run is a no-op. Chained
onto 273 (the ideation product-binding head) so the alembic graph stays a
single linear head - see the dual-head / down_revision lessons in
LESSONS-LEARNT.md.

See documentation/plans/ideation/PLAN-ideation-ideate-intent.md.

Revision ID: 274_ideation_workspace_config
Revises: 273_ideation_product_binding
Create Date: 2026-07-19
"""
from alembic import op

revision = "274_ideation_workspace_config"
down_revision = "273_ideation_product_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_shared_service_url VARCHAR(512)"
    )
    op.execute(
        "ALTER TABLE respond_workspaces "
        "ADD COLUMN IF NOT EXISTS ideation_intake_api_key_ciphertext TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE respond_workspaces "
        "DROP COLUMN IF EXISTS ideation_intake_api_key_ciphertext"
    )
    op.execute(
        "ALTER TABLE respond_workspaces "
        "DROP COLUMN IF EXISTS ideation_shared_service_url"
    )
