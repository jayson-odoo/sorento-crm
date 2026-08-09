"""Warranty configuration (S7b): the duration XOR constraint and the eight slugs.

Two things, and the second is the one that is easy to get wrong.

**1. `ck_warranty_terms_duration_xor_lifetime` (AC-P3a / AC-P19).** A term is either
lifetime or a positive number of months, never both and never neither. Measured
2026-08-09 and re-measured before this migration was written: all **41** existing
`warranty_terms` rows satisfy it, so the constraint is written. Had any row failed,
the constraint would have been dropped from the slice and said so - editing live
rows to fit a constraint nobody asked for is not a migration.

The same constraint is declared on `WarrantyTerm.__table_args__`. Not
belt-and-braces: CI builds its schema from `Base.metadata.create_all` and then
stamps alembic at head WITHOUT executing a migration body, so a constraint living
only here would exist on a developer machine and on prod and on no test database
anywhere - and the raw-INSERT test proving the database rejects a bad row would pass
by absence.

`duration_months IS NOT NULL` is spelled out rather than left to `> 0`: a CHECK
passes when it evaluates to NULL, so the shorter form would silently ADMIT the
neither-nor row it exists to refuse.

**2. The eight permission slugs, GRANTED.** `sync_permissions` seeds a slug and
grants it to NOBODY, so a migration that only called it would ship a screen every
non-admin is locked out of - and superadmin/admin bypass `require_permission`
entirely, which means nobody would notice in testing (AC-X4, DoD gate 3).

The role split is AC-P23's, not the implementer's: view/add/edit reach the four
management-shaped roles (migration 236's precedent), and the two `.delete` slugs
reach admin and director ONLY - deleting a Policy cascades its Terms, and deleting a
Kind is refused precisely because it would rewrite the policy document.

Revision ID: 331_warranty_config
Revises: 330_resolution_requires_service_job
Create Date: 2026-08-09
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "331_warranty_config"
down_revision = "330_resolution_requires_service_job"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_warranty_terms_duration_xor_lifetime"
_CHECK_SQL = (
    "(is_lifetime AND duration_months IS NULL) OR "
    "(NOT is_lifetime AND duration_months IS NOT NULL AND duration_months > 0)"
)

# AC-P23. The four management-shaped roles that may CONFIGURE warranty.
_GRANT_ROLE_SLUGS = ("admin", "director", "management", "manager")
# AC-P23. The narrower set that may DELETE. A manager who can delete a published
# policy takes its terms with it.
_DELETE_ROLE_SLUGS = ("admin", "director")

_MANAGE_SLUGS = (
    "warranty.policies.view",
    "warranty.policies.add",
    "warranty.policies.edit",
    "warranty.kinds.view",
    "warranty.kinds.add",
    "warranty.kinds.edit",
)
_DELETE_SLUGS = (
    "warranty.policies.delete",
    "warranty.kinds.delete",
)

# Mirrors app/rbac/permission_registry.py::_crud("warranty", ...). Spelled out here
# rather than imported, so the migration keeps working if the registry is later
# reshaped - a migration reads the world as it was on the day it ran.
_PERMISSION_NAMES = {
    "warranty.policies.view": ("View Warranty Policies", "Permission to view Warranty Policies."),
    "warranty.policies.add": ("Add Warranty Policies", "Permission to add Warranty Policies."),
    "warranty.policies.edit": ("Edit Warranty Policies", "Permission to edit Warranty Policies."),
    "warranty.policies.delete": ("Delete Warranty Policies", "Permission to delete Warranty Policies."),
    "warranty.kinds.view": ("View Warranty Product Kinds", "Permission to view Warranty Product Kinds."),
    "warranty.kinds.add": ("Add Warranty Product Kinds", "Permission to add Warranty Product Kinds."),
    "warranty.kinds.edit": ("Edit Warranty Product Kinds", "Permission to edit Warranty Product Kinds."),
    "warranty.kinds.delete": ("Delete Warranty Product Kinds", "Permission to delete Warranty Product Kinds."),
}


def _ensure_permission(conn, slug: str, now) -> str:
    row = conn.execute(
        sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
    ).fetchone()
    if row is not None:
        return row.id
    name, description = _PERMISSION_NAMES[slug]
    permission_id = str(uuid.uuid4())
    conn.execute(
        sa.text(
            "INSERT INTO user_permissions (id, slug, name, description, created_at) "
            "VALUES (:id, :slug, :name, :desc, :now)"
        ),
        {"id": permission_id, "slug": slug, "name": name, "desc": description, "now": now},
    )
    return permission_id


def _grant(conn, permission_id: str, role_slugs, now) -> None:
    role_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug IN :slugs").bindparams(
                sa.bindparam("slugs", expanding=True)
            ),
            {"slugs": list(role_slugs)},
        ).fetchall()
    ]
    for role_id in role_ids:
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM user_role_permissions "
                "WHERE role_id = :r AND permission_id = :p"
            ),
            {"r": role_id, "p": permission_id},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO user_role_permissions "
                    "(id, role_id, permission_id, assigned_at) "
                    "VALUES (:id, :r, :p, :now)"
                ),
                {"id": str(uuid.uuid4()), "r": role_id, "p": permission_id, "now": now},
            )


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()

    already = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = 'warranty_terms' AND c.conname = :name"
        ),
        {"name": _CHECK_NAME},
    ).fetchone()
    if not already:
        op.create_check_constraint(_CHECK_NAME, "warranty_terms", sa.text(_CHECK_SQL))

    for slug in _MANAGE_SLUGS:
        _grant(conn, _ensure_permission(conn, slug, now), _GRANT_ROLE_SLUGS, now)
    for slug in _DELETE_SLUGS:
        _grant(conn, _ensure_permission(conn, slug, now), _DELETE_ROLE_SLUGS, now)


def downgrade() -> None:
    conn = op.get_bind()

    still_there = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = 'warranty_terms' AND c.conname = :name"
        ),
        {"name": _CHECK_NAME},
    ).fetchone()
    if still_there:
        op.drop_constraint(_CHECK_NAME, "warranty_terms", type_="check")

    for slug in _MANAGE_SLUGS + _DELETE_SLUGS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is not None:
            conn.execute(
                sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"),
                {"p": row.id},
            )
            conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": row.id})
