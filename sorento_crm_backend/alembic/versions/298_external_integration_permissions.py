"""Register and grant the integration.* permissions used by /external

AC-AC-05 requires every /api/v1/external endpoint to enforce a permission. Most
mapped onto existing slugs, but six capabilities are exposed only to integration
callers and had no human-facing screen, so no slug existed:

    integration.storage.presign
    integration.assignment.resolve
    integration.conversation_context.edit
    integration.contacts.sync
    integration.semantic_search.use
    integration.ideation.submit

Registering them is not enough. Permissions are computed at provision time and
do NOT reach existing roles automatically -- so a new permission with no grant
path silently 403s the very feature it was meant to protect, and the failure
looks like a broken integration rather than a missing grant. This migration
therefore grants them explicitly to:

  * Admin -- which is what the shared key resolves to today, so enforcement
    cannot regress live n8n or MCP traffic at cutover
  * every integration_* role seeded by migration 297

Revision ID: 298_external_integration_permissions
Revises: 297_seed_integrations
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "298_external_integration_permissions"
down_revision = "297_seed_integrations"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_NEW_SLUGS = [
    "integration.storage.presign",
    "integration.assignment.resolve",
    "integration.conversation_context.edit",
    "integration.contacts.sync",
    "integration.semantic_search.use",
    "integration.ideation.submit",
]


def upgrade():
    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        created = sync_permissions(session)
        logger.info("298: registered %d new permission(s)", created)

        permission_ids = {
            row[0]: row[1]
            for row in session.execute(
                sa.text("SELECT slug, id FROM user_permissions WHERE slug = ANY(:slugs)"),
                {"slugs": _NEW_SLUGS},
            )
        }
        missing = set(_NEW_SLUGS) - set(permission_ids)
        if missing:
            # Fail loudly: the guards reference these slugs, so a role that can
            # never hold them means a permanently 403ing endpoint.
            raise RuntimeError(f"298: permissions failed to register: {sorted(missing)}")

        target_roles = [
            row[0]
            for row in session.execute(
                sa.text(
                    "SELECT id FROM user_roles "
                    "WHERE slug = 'admin' OR slug LIKE 'integration\\_%'"
                )
            )
        ]
        if not target_roles:
            logger.warning("298: no admin or integration roles found; granted nothing")

        granted = 0
        for role_id in target_roles:
            for slug, permission_id in permission_ids.items():
                exists = session.execute(
                    sa.text(
                        "SELECT 1 FROM user_role_permissions "
                        "WHERE role_id = :r AND permission_id = :p"
                    ),
                    {"r": role_id, "p": permission_id},
                ).first()
                if exists:
                    continue
                session.execute(
                    sa.text(
                        "INSERT INTO user_role_permissions (id, role_id, permission_id) "
                        "VALUES (gen_random_uuid()::text, :r, :p)"
                    ),
                    {"r": role_id, "p": permission_id},
                )
                granted += 1

        session.commit()
        logger.info("298: granted %d role-permission pair(s) across %d role(s)", granted, len(target_roles))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": _NEW_SLUGS},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": _NEW_SLUGS},
    )
