"""Register and grant user_management.contacts.view + .reference_data.view

`documentation/plans/security/PLAN-user-management-read-gates.md` deferred two
questions (Q1 and Q3) because the routes involved had no slug to gate on. Both
are now decided: gate them. This migration registers the two new slugs and,
critically, GRANTS them - migration 298 is explicit that registering a
permission does NOT reach existing roles automatically, so a new slug with no
grant path silently 403s the very feature it was meant to protect.

`user_management.contacts.view` (Q1) gates the eight contacts GETs. Its grant
list is the roles that legitimately administer the contact directory today:
admin, superadmin, director, warehouse_manager and the three integration_*
roles seeded by migration 297 - the same set that already holds the sibling
`user_management.*.view` slugs. It is deliberately NOT granted to every role
that can currently reach the screen (the topbar Apps dropdown renders it for
all 125 assigned users with no filter), because that reach is the defect, not
the requirement.

`user_management.reference_data.view` (Q3) gates the two shared reference
catalogs, `GET /contact-access-types/` and `GET /market-segments/`. These are
read by roughly ten screens OUTSIDE user-management - marketing promotions,
forms, resource-management files / attachment directories / attachment types,
master-data brands and products - plus the in-package screens that front the
same two catalogs (the contact detail page's market-segment section and edit
dialog, and the access-agents member segment editor), so a grant list narrower
than "everyone who can open one of those screens" would break a picker on a page
the role is otherwise fully entitled to. The grant set is therefore DERIVED IN
SQL: every role holding at least one of

    forms.forms.view
    marketing.promotions.view
    master_data.brands.view
    master_data.products.view
    resource.attachments.view
    resource.attachment_directories.view
    resource.attachment_types.view
    user_management.contacts.view
    user_management.access_agents.view

The derivation deliberately runs AFTER the contacts.view grant below and in the
same transaction, so a role this migration itself grants contacts.view to is
visible to the SELECT and receives reference_data.view in the same run.

On the production-shaped role set that resolves to admin, superadmin, director,
warehouse_manager, marketing_manager, marketing_executive, purchasing_manager,
purchasing_executive, warehouse_executive and the three integration_* roles -
but it is DERIVED, not typed out, so an install with a different or renamed
role set gets its own right answer instead of a list copied from this repo's
production data. (admin and superadmin bypass `check_user_has_permission`
outright, so their rows here are for completeness of the roles screen, not for
enforcement.)

Roles named in the contacts list but absent from the database are skipped with a
log line, never a crash - a fresh install carrying none of these roles, and one
whose roles hold none of the consumer slugs, must both still upgrade cleanly.

Revision ID: 359_um_contacts_reference_perms
Revises: 358_scm_po_spo_history_aliases
"""
import logging

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

revision = "359_um_contacts_reference_perms"
down_revision = "358_scm_po_spo_history_aliases"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

_CONTACTS_VIEW = "user_management.contacts.view"
_REFERENCE_DATA_VIEW = "user_management.reference_data.view"

_NEW_SLUGS = [_CONTACTS_VIEW, _REFERENCE_DATA_VIEW]

# Hardcoded, per the decision above: who may read the contact directory.
_CONTACTS_VIEW_ROLE_SLUGS = [
    "admin",
    "superadmin",
    "director",
    "warehouse_manager",
    "integration_foundryx_esb",
    "integration_n8n",
    "integration_sorento_mcp",
]

# Derived, per the decision above: the screens that consume the shared catalogs.
_REFERENCE_CONSUMER_SLUGS = [
    "forms.forms.view",
    "marketing.promotions.view",
    "master_data.brands.view",
    "master_data.products.view",
    "resource.attachments.view",
    "resource.attachment_directories.view",
    "resource.attachment_types.view",
    _CONTACTS_VIEW,
    "user_management.access_agents.view",
]


def _role_ids_by_slug(session, role_slugs: list[str]) -> dict[str, str]:
    rows = session.execute(
        sa.text("SELECT slug, id FROM user_roles WHERE slug = ANY(:slugs)"),
        {"slugs": role_slugs},
    )
    return {row[0]: row[1] for row in rows}


def _grant(session, role_ids: set[str], permission_id: str) -> int:
    """Insert missing (role, permission) pairs. Idempotent: re-running inserts
    nothing, matching migration 298's guard style."""
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
        logger.info("359: registered %d new permission(s)", created)

        permission_ids = {
            row[0]: row[1]
            for row in session.execute(
                sa.text("SELECT slug, id FROM user_permissions WHERE slug = ANY(:slugs)"),
                {"slugs": _NEW_SLUGS},
            )
        }
        missing = set(_NEW_SLUGS) - set(permission_ids)
        if missing:
            # Fail loudly: the route dependencies reference these slugs, so a
            # permission no role can ever hold is a permanently 403ing endpoint.
            raise RuntimeError(f"359: permissions failed to register: {sorted(missing)}")

        # --- contacts.view: hardcoded role list ---------------------------
        contacts_roles = _role_ids_by_slug(session, _CONTACTS_VIEW_ROLE_SLUGS)
        for slug in _CONTACTS_VIEW_ROLE_SLUGS:
            if slug not in contacts_roles:
                logger.info("359: role %r not present in this install; skipped for %s", slug, _CONTACTS_VIEW)
        if not contacts_roles:
            logger.warning("359: none of the %s roles exist; granted nothing", _CONTACTS_VIEW)
        contacts_granted = _grant(session, set(contacts_roles.values()), permission_ids[_CONTACTS_VIEW])

        # --- reference_data.view: role set derived from the consumer slugs --
        # Must stay AFTER the contacts grant above: contacts.view is itself a
        # consumer slug, so a role granted it in this run has to be visible here.
        derived_rows = session.execute(
            sa.text(
                "SELECT DISTINCT r.id, r.slug FROM user_roles r "
                "JOIN user_role_permissions rp ON rp.role_id = r.id "
                "JOIN user_permissions p ON p.id = rp.permission_id "
                "WHERE p.slug = ANY(:consumer_slugs)"
            ),
            {"consumer_slugs": _REFERENCE_CONSUMER_SLUGS},
        ).all()
        reference_role_ids = {row[0] for row in derived_rows}
        derived_slugs = sorted(row[1] for row in derived_rows)

        if not reference_role_ids:
            logger.warning(
                "359: no role holds any of %s; granted nothing for %s",
                _REFERENCE_CONSUMER_SLUGS,
                _REFERENCE_DATA_VIEW,
            )
        else:
            logger.info("359: %s derived from consumer grants: %s", _REFERENCE_DATA_VIEW, derived_slugs)
        reference_granted = _grant(session, reference_role_ids, permission_ids[_REFERENCE_DATA_VIEW])

        session.commit()
        logger.info(
            "359: granted %s to %d role(s) (%d new row(s)); %s to %d role(s) (%d new row(s))",
            _CONTACTS_VIEW,
            len(contacts_roles),
            contacts_granted,
            _REFERENCE_DATA_VIEW,
            len(reference_role_ids),
            reference_granted,
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
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": _NEW_SLUGS},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"),
        {"slugs": _NEW_SLUGS},
    )
