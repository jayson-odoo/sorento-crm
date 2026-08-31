"""Register user_management.reference_data.manage and grant it (issue #402).

`market_segment.delete` (S6b's deferred record action, `app/services/record_actions.py`)
authorised a hard delete with `user_management.reference_data.view` - a READ grant
permitting a WRITE, which was wrong in principle even though the immediate
`DELETE /market-segments/{code}` route it replaced carried no slug at all.

This registers the narrower `.manage` slug and enforces it on both the route and
the handler (same change, same commit - a slug with no grant path is a
permanently 403ing feature, per migration 298 and 359's own note). The grant set
is DERIVED, not typed out, same as 359's `reference_data.view` derivation:
every role that holds `reference_data.view` TODAY receives `.manage` too, so
nobody who could delete a market segment before this migration loses the
ability, and an install with a different role set gets its own right answer
instead of a list copied from this repo's production data.

This is deliberately generous - a role holding `.view` for an unrelated reason
(reading the catalog from a picker) also receives `.manage` - because `.view`
was ALREADY the de facto authority to delete before this migration, and this is
a delete-path fix, not a new restriction. Narrowing which roles may WRITE the
catalog, if that is ever wanted, is a separate, deliberate grant sweep.

Revision ID: s6b_reference_data_manage_perm
Revises: s6b_record_action_entity_id
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "s6b_reference_data_manage_perm"
down_revision = "s6b_record_action_entity_id"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_REFERENCE_DATA_VIEW = "user_management.reference_data.view"
_REFERENCE_DATA_MANAGE = "user_management.reference_data.manage"


def _grant(session, role_ids: set[str], permission_id: str) -> int:
    """Insert missing (role, permission) pairs. Idempotent: re-running inserts
    nothing, matching migration 298/359's guard style."""
    granted = 0
    for role_id in sorted(role_ids):
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
    return granted


def upgrade():
    from app.rbac.permission_registry import sync_permissions

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        created = sync_permissions(session)
        logger.info("s6b-ref-manage: registered %d new permission(s)", created)

        manage_row = session.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"),
            {"s": _REFERENCE_DATA_MANAGE},
        ).first()
        if manage_row is None:
            raise RuntimeError(
                f"s6b-ref-manage: {_REFERENCE_DATA_MANAGE!r} failed to register"
            )
        manage_id = manage_row[0]

        # Derived: every role that already holds reference_data.view.
        view_roles = session.execute(
            sa.text(
                "SELECT DISTINCT r.id, r.slug FROM user_roles r "
                "JOIN user_role_permissions rp ON rp.role_id = r.id "
                "JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE p.slug = :s"
            ),
            {"s": _REFERENCE_DATA_VIEW},
        ).all()
        role_ids = {row[0] for row in view_roles}
        role_slugs = sorted(row[1] for row in view_roles)

        if not role_ids:
            logger.warning(
                "s6b-ref-manage: no role holds %s; granted %s to nobody",
                _REFERENCE_DATA_VIEW,
                _REFERENCE_DATA_MANAGE,
            )
        else:
            logger.info(
                "s6b-ref-manage: %s derived from %s holders: %s",
                _REFERENCE_DATA_MANAGE,
                _REFERENCE_DATA_VIEW,
                role_slugs,
            )
        granted = _grant(session, role_ids, manage_id)

        session.commit()
        logger.info(
            "s6b-ref-manage: granted %s to %d role(s) (%d new row(s))",
            _REFERENCE_DATA_MANAGE,
            len(role_ids),
            granted,
        )
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
            "(SELECT id FROM user_permissions WHERE slug = :s)"
        ),
        {"s": _REFERENCE_DATA_MANAGE},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = :s"),
        {"s": _REFERENCE_DATA_MANAGE},
    )
