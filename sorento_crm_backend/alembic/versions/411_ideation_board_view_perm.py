"""Seed ideation.board.view permission slug and grant to admin roles.

The Ideas embed route was gated on ``get_current_user`` only. This migration
seeds the ``ideation.board.view`` permission slug and grants it to
``superadmin`` and ``admin`` roles so the new ``require_permission`` gate on
the route does not silently 403 for already-provisioned users (PRINCIPLES
DoD #3).

Revision ID: 411_idea_board_perm
Revises: 410_trgm_norm_idx
Create Date: 2026-08-24
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "411_idea_board_perm"
down_revision = "410_trgm_norm_idx"
branch_labels = None
depends_on = None

_PERMS = [
    ("ideation.board.view", "View the Ideas board", "View the Ideas board and open individual ideas."),
]

_GRANT_ROLES = ("superadmin", "admin")


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    perm_ids: list[str] = []

    for slug, name, desc in _PERMS:
        row = conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
        ).fetchone()
        if row is None:
            pid = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_permissions (id, slug, name, description, created_at)
                    VALUES (:id, :slug, :name, :desc, :now)
                    ON CONFLICT (slug) DO NOTHING
                    """
                ),
                {"id": pid, "slug": slug, "name": name, "desc": desc, "now": now},
            )
            row = conn.execute(
                sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}
            ).fetchone()
        perm_ids.append(row.id)

    role_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug = ANY(:slugs)"),
            {"slugs": list(_GRANT_ROLES)},
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
            sa.text("SELECT id FROM user_permissions WHERE slug = ANY(:s)"),
            {"s": slugs},
        ).fetchall()
    ]
    if perm_ids:
        conn.execute(
            sa.text("DELETE FROM user_role_permissions WHERE permission_id = ANY(:p)"),
            {"p": perm_ids},
        )
        conn.execute(
            sa.text("DELETE FROM user_permissions WHERE id = ANY(:p)"),
            {"p": perm_ids},
        )
