"""Seed integration principals, roles and the legacy shared key

Reads EXTERNAL_API_KEY **once, here, at migration time** and stores its hash as
the `legacy-shared-key` integration, acting as the same principal it acts as
today. n8n and the MCP server therefore keep working with zero changes, while
no runtime code path ever reads the env var again.

That is what dissolves the AC-AC-01 / AC-AC-09 conflict rather than trading one
against the other, and it is why no dual-accept fallback is written: a
deprecation fallback nobody is scheduled to remove outlives its removal date.

The seeded roles copy Admin's permission set -- parity with what the shared key
grants today, so nothing regresses at cutover. This is explicitly NOT least
privilege: n8n and the MCP server remain Admin-equivalent until their real
endpoint usage is confirmed and their roles narrowed. Tracked as follow-up.

If EXTERNAL_API_KEY is absent, no legacy key is seeded and the migration logs
loudly. It never writes an empty hash -- that would be an authentication bypass,
not a missing feature.

Revision ID: 297_seed_integrations
Revises: 296_integrations_and_api_keys
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "297_seed_integrations"
down_revision = "296_integrations_and_api_keys"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")


def upgrade():
    from app.config import settings
    from app.services.integration_seed import seed_integrations

    bind = op.get_bind()
    session = Session(bind=bind)

    # The principal today's shared key already acts as. Pointing the legacy row
    # anywhere else would silently change what current callers may do at the
    # exact moment of cutover.
    legacy_act_as = getattr(settings, "external_api_key_act_as_user_id", None) or None
    if legacy_act_as:
        exists = session.execute(
            sa.text("SELECT 1 FROM users WHERE id = :uid"), {"uid": legacy_act_as}
        ).first()
        if not exists:
            logger.warning(
                "seed_integrations: EXTERNAL_API_KEY_ACT_AS_USER_ID=%s not found in users; "
                "the legacy integration will have no principal and will refuse requests.",
                legacy_act_as,
            )
            legacy_act_as = None

    try:
        seed_integrations(
            session,
            external_api_key=getattr(settings, "external_api_key", None),
            legacy_act_as_user_id=legacy_act_as,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade():
    # Remove only what this migration seeded, and only by the names it used.
    # Keys cascade with their integration.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM integrations WHERE name IN "
            "('n8n', 'sorento-mcp', 'foundryx-esb', 'legacy-shared-key')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM user_role_assignments WHERE user_id IN "
            "(SELECT id FROM users WHERE is_integration = true)"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE role_id IN "
            "(SELECT id FROM user_roles WHERE slug LIKE 'integration\\_%')"
        )
    )
    bind.execute(sa.text("DELETE FROM user_roles WHERE slug LIKE 'integration\\_%'"))
    bind.execute(sa.text("DELETE FROM users WHERE is_integration = true"))
