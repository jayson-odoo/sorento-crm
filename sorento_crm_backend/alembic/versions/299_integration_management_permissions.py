"""Register and grant integration.integrations.* management permissions

Adds view/add/edit/delete plus manage_keys for the integration management
screen (AC-AC-08).

Granted to **Admin only**. Deliberately NOT to the integration_* roles: an
integration that could manage integrations could mint itself a credential with
a different principal, or read the roster of every other caller. A compromise
of one integration would then escalate into a compromise of all of them, which
is exactly the blast radius Group A exists to contain.

That distinction survives only because permissions do not propagate to existing
roles automatically -- the integration roles were seeded as a copy of Admin's
permission set at that moment, not as a live alias of it. Anything added later
must be granted deliberately, which is what makes this narrowing possible.

manage_keys is separate from edit for the same reason: renaming an integration
and issuing a working credential for it are different levels of trust.

Revision ID: 299_integration_management_permissions
Revises: 298_external_integration_permissions
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "299_integration_management_permissions"
down_revision = "298_external_integration_permissions"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_SLUGS = [
    "integration.integrations.view",
    "integration.integrations.add",
    "integration.integrations.edit",
    "integration.integrations.delete",
    "integration.integrations.manage_keys",
]


def upgrade():
    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        sync_permissions(session)

        permission_ids = [
            row[0]
            for row in session.execute(
                sa.text("SELECT id FROM user_permissions WHERE slug = ANY(:slugs)"),
                {"slugs": _SLUGS},
            )
        ]
        if len(permission_ids) != len(_SLUGS):
            raise RuntimeError(
                f"299: expected {len(_SLUGS)} permissions, registered {len(permission_ids)}"
            )

        admin_roles = [
            row[0]
            for row in session.execute(
                sa.text("SELECT id FROM user_roles WHERE slug = 'admin'")
            )
        ]
        if not admin_roles:
            logger.warning("299: no admin role found; the management screen will 403 for everyone")

        granted = 0
        for role_id in admin_roles:
            for permission_id in permission_ids:
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
        logger.info("299: granted %d management permission(s) to Admin", granted)
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
        {"slugs": _SLUGS},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": _SLUGS},
    )
