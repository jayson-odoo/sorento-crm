"""Permissions for the import column mappings page (S5, AC-E1).

`.view` is swept onto every role that already holds the sibling
`system.numbering_rules.view` - both pages are the same kind of admin surface (a rule that
shapes how an importer reads a file), and seeing which header means which field is
harmless.

`.edit` is NOT swept (security review, fix round 1): a mapping row changes how EVERY later
import of that document type is read, for every company, and a wrong one silently mis-reads
a column on every file from then on. That is an administrator's decision, so it goes to
`admin` and `superadmin` only and is widened by hand from the roles page if somebody else
needs it.

Revision ID: 505_import_field_aliases_perms
Revises: 504_ship_line_prod_sup_nonuniq
Create Date: 2026-09-10
"""
from alembic import op
import sqlalchemy as sa

revision = "505_import_field_aliases_perms"
down_revision = "504_ship_line_prod_sup_nonuniq"
branch_labels = None
depends_on = None

_PERMISSIONS = [
    (
        "system.import_field_aliases.view",
        "View Import Column Mappings",
        "Permission to view which header spellings resolve to which import field, per document type.",
    ),
    (
        "system.import_field_aliases.edit",
        "Edit Import Column Mappings",
        "Permission to add or remove a header-to-field mapping for a document type's importer.",
    ),
]
#: (new slug, sibling slug already granted to the roles that should get it too).
_SWEEP = [
    ("system.import_field_aliases.view", "system.numbering_rules.view"),
]
#: Roles that get `.edit` - named, not swept. See the module docstring.
_EDIT_ROLE_SLUGS = ("admin", "superadmin")
_EXCLUDED_ROLE_PREFIX = "integration\\_%"


def _insert_permission(bind, slug: str, name: str, description: str) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": slug, "name": name, "descr": description},
    )


def _sweep(bind, target: str, source: str) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :source
            JOIN user_roles r ON r.id = rp.role_id
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :target
              AND r.slug NOT LIKE :excluded
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"source": source, "target": target, "excluded": _EXCLUDED_ROLE_PREFIX},
    )


def _grant_to_roles(bind, slug: str, role_slugs: tuple[str, ...]) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE p.slug = :slug AND r.slug = ANY(:roles)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slug": slug, "roles": list(role_slugs)},
    )


def upgrade() -> None:
    bind = op.get_bind()
    for slug, name, description in _PERMISSIONS:
        _insert_permission(bind, slug, name, description)
    for target, source in _SWEEP:
        _sweep(bind, target, source)
    _grant_to_roles(bind, "system.import_field_aliases.edit", _EDIT_ROLE_SLUGS)


def downgrade() -> None:
    bind = op.get_bind()
    slugs = [slug for slug, _, _ in _PERMISSIONS]
    bind.execute(
        sa.text(
            "DELETE FROM user_role_permissions WHERE permission_id IN "
            "(SELECT id FROM user_permissions WHERE slug = ANY(:slugs))"
        ),
        {"slugs": slugs},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = ANY(:slugs)"), {"slugs": slugs}
    )
