"""Move the carried-over EXTERNAL_API_KEY from legacy-shared-key onto n8n

Migration 297 parked the existing env key on a shared `legacy-shared-key` row so
both n8n and the MCP server kept working. That works, but it makes the two
callers indistinguishable in the audit trail, which defeats AC-AC-02/38 for
exactly the callers that matter most today.

Only one integration can hold that value (key_hash is unique), so it goes to the
caller that is expensive to migrate: n8n has the key pasted as a literal across
~40 workflow nodes, while the MCP server reads it from a single env var on one
service. n8n therefore keeps working untouched *and* is correctly attributed;
the MCP server takes its own key at deploy time.

Known consequence, stated plainly: until the MCP server is issued its own key it
presents the same value and will authenticate as n8n. That is an attribution
inaccuracy, not an access grant -- both roles are Admin-equivalent today.

Idempotent and safe on a database that never had the legacy row (fresh installs
seed straight onto n8n).

Revision ID: 300_env_key_belongs_to_n8n
Revises: 299_integration_management_permissions
"""
import logging

import sqlalchemy as sa
from alembic import op

revision = "300_env_key_belongs_to_n8n"
down_revision = "299_integration_management_permissions"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade():
    bind = op.get_bind()

    legacy_id = bind.execute(
        sa.text("SELECT id FROM integrations WHERE name = 'legacy-shared-key'")
    ).scalar()
    if legacy_id is None:
        logger.info("300: no legacy-shared-key row; nothing to move")
        return

    n8n_id = bind.execute(
        sa.text("SELECT id FROM integrations WHERE name = 'n8n'")
    ).scalar()
    if n8n_id is None:
        # Leave the legacy row intact rather than orphaning a working key --
        # deleting it here would silently break every current caller.
        logger.warning("300: no n8n integration found; leaving legacy row untouched")
        return

    moved = bind.execute(
        sa.text(
            "UPDATE integration_api_keys SET integration_id = :n8n "
            "WHERE integration_id = :legacy"
        ),
        {"n8n": n8n_id, "legacy": legacy_id},
    ).rowcount

    bind.execute(
        sa.text("DELETE FROM integrations WHERE id = :legacy"), {"legacy": legacy_id}
    )
    logger.info("300: moved %d key(s) to n8n and removed the legacy row", moved)


def downgrade():
    """Recreate the legacy row and move the key back.

    The key's principal is whatever n8n acts as; the original legacy row pointed
    at the EXTERNAL_API_KEY_ACT_AS_USER_ID principal. Reconstructing that exactly
    is not possible from the database alone, so the restored row reuses n8n's
    principal. Authentication continues to work; only the attributed user differs.
    """
    bind = op.get_bind()

    n8n = bind.execute(
        sa.text("SELECT id, act_as_user_id FROM integrations WHERE name = 'n8n'")
    ).first()
    if n8n is None:
        return

    bind.execute(
        sa.text(
            "INSERT INTO integrations (id, name, type, status, act_as_user_id, is_active, created_at, updated_at) "
            "VALUES (gen_random_uuid(), 'legacy-shared-key', 'legacy', 'UNVERIFIED', :u, true, now(), now()) "
            "ON CONFLICT (name) DO NOTHING"
        ),
        {"u": n8n[1]},
    )
    legacy_id = bind.execute(
        sa.text("SELECT id FROM integrations WHERE name = 'legacy-shared-key'")
    ).scalar()
    bind.execute(
        sa.text(
            "UPDATE integration_api_keys SET integration_id = :legacy "
            "WHERE integration_id = :n8n"
        ),
        {"legacy": legacy_id, "n8n": n8n[0]},
    )
