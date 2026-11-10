"""Seed the dashboards.town.view permission and grant it to the admin roles.

The Town is admin-only (owner, 10 Nov 2026, TOWN-V2): `GET /api/v1/town/snapshot` now requires
`dashboards.town.view`, and the Town menu item and page are gated on it. Seeded here so already
provisioned installs keep the admin roles' access the moment the gate ships (PRINCIPLES DoD #3);
no other role is granted it.

Revision ID: town_0001_view_perm
Revises: ptag_0021_icon_conditions
Create Date: 2026-11-10
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "town_0001_view_perm"
down_revision = "ptag_0021_icon_conditions"
branch_labels = None
depends_on = None

_PERMS = [
    (
        "dashboards.town.view",
        "View the Town",
        "See the Town: today's sales, dealers, stock, deliveries, approvals and incoming shipments, "
        "and its wallboard mode.",
    ),
]

_GRANT_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    perm_ids: list[str] = []

    for slug, name, desc in _PERMS:
        conn.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                VALUES (:id, :slug, :name, :desc, :now)
                ON CONFLICT (slug) DO NOTHING
                """
            ),
            {"id": str(uuid.uuid4()), "slug": slug, "name": name, "desc": desc, "now": now},
        )
        perm_ids.append(
            conn.execute(sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}).scalar_one()
        )

    role_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug = ANY(:slugs)"), {"slugs": list(_GRANT_ROLES)}
        ).fetchall()
    ]
    for rid in role_ids:
        for pid in perm_ids:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                    VALUES (:id, :r, :p, :now)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                    """
                ),
                {"id": str(uuid.uuid4()), "r": rid, "p": pid, "now": now},
            )


def downgrade() -> None:
    conn = op.get_bind()
    slugs = [slug for slug, _, _ in _PERMS]
    perm_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = ANY(:s)"), {"s": slugs}
        ).fetchall()
    ]
    if perm_ids:
        conn.execute(sa.text("DELETE FROM user_role_permissions WHERE permission_id = ANY(:p)"), {"p": perm_ids})
        conn.execute(sa.text("DELETE FROM user_permissions WHERE id = ANY(:p)"), {"p": perm_ids})
