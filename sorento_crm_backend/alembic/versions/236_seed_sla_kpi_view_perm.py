"""Seed `sla.kpi.view` permission (management KPI dashboard, TCK-32).

Granted to management-style roles (admin / director / management / manager by
slug). superadmin/admin bypass require_permission regardless; this grant lets
non-admin management roles see the dashboard. Tighten/loosen via the RBAC UI.

Revision ID: 236_seed_sla_kpi_view_perm
Revises: 235_form_sla_event_trigger_and_escalate_perm
Create Date: 2026-06-17
"""
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "236_seed_sla_kpi_view_perm"
down_revision = "235_form_sla_event_trigger_and_escalate_perm"
branch_labels = None
depends_on = None

_PERM_SLUG = "sla.kpi.view"
_GRANT_ROLE_SLUGS = ("admin", "director", "management", "manager")


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    perm = conn.execute(
        sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _PERM_SLUG}
    ).fetchone()
    if perm is None:
        perm_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO user_permissions (id, slug, name, description, created_at) "
                "VALUES (:id, :slug, :name, :desc, :now)"
            ),
            {"id": perm_id, "slug": _PERM_SLUG, "name": "View SLA KPI dashboard",
             "desc": "View the management SLA KPI dashboard.", "now": now},
        )
    else:
        perm_id = perm.id

    role_ids = [
        r.id for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug IN :slugs").bindparams(
                sa.bindparam("slugs", expanding=True)
            ),
            {"slugs": list(_GRANT_ROLE_SLUGS)},
        ).fetchall()
    ]
    for rid in role_ids:
        exists = conn.execute(
            sa.text("SELECT 1 FROM user_role_permissions WHERE role_id = :r AND permission_id = :p"),
            {"r": rid, "p": perm_id},
        ).fetchone()
        if not exists:
            conn.execute(
                sa.text(
                    "INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at) "
                    "VALUES (:id, :r, :p, :now)"
                ),
                {"id": str(uuid.uuid4()), "r": rid, "p": perm_id, "now": now},
            )


def downgrade() -> None:
    conn = op.get_bind()
    perm = conn.execute(
        sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _PERM_SLUG}
    ).fetchone()
    if perm is not None:
        conn.execute(sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"), {"p": perm.id})
        conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": perm.id})
