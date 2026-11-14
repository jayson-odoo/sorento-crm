"""Seed ideation.ideas.submit; grant it to portal_user and ideation.board.view to salesperson.

WA-COMPLAINT-INTAKE D-1 (owner 13 Nov: D1 (a), Q2 (a)). A dealer files a feature request or an issue
on WhatsApp as its own CRM user, created with role ``portal_user`` only; ``ideation.ideas.submit`` is
what lets that user file (the capture gate) and opens no Ideas page. Salespeople get the Ideas board.
``portal_user`` is never given ``ideation.board.view``. Idempotent; follows 411_ideation_board_view_perm.

Revision ID: wa_0001_idea_submit_perm
Revises: agent_0001_proposal_insights
Create Date: 2026-11-13
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "wa_0001_idea_submit_perm"
down_revision = "agent_0001_proposal_insights"
branch_labels = None
depends_on = None

_SUBMIT = (
    "ideation.ideas.submit",
    "Submit ideas and issues",
    "File a feature request or an issue through the WhatsApp assistant. Opens no Ideas page.",
)
_VIEW = ("ideation.board.view", "View the Ideas board", "View the Ideas board and open individual ideas.")
#: (permission, role slug) pairs this migration grants.
_GRANTS = ((_SUBMIT, "portal_user"), (_VIEW, "salesperson"))


def _permission_id(conn, slug: str, name: str, desc: str, now) -> str:
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
    return conn.execute(sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}).scalar()


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.utcnow()
    for (slug, name, desc), role_slug in _GRANTS:
        pid = _permission_id(conn, slug, name, desc, now)
        rid = conn.execute(sa.text("SELECT id FROM user_roles WHERE slug = :s"), {"s": role_slug}).scalar()
        if rid is None:
            continue
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
    # The board grant to salesperson goes; the board slug itself stays (411 owns it).
    conn.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE role_id = (SELECT id FROM user_roles WHERE slug = 'salesperson')
              AND permission_id = (SELECT id FROM user_permissions WHERE slug = :view)
            """
        ),
        {"view": _VIEW[0]},
    )
    pid = conn.execute(sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": _SUBMIT[0]}).scalar()
    if pid is not None:
        conn.execute(sa.text("DELETE FROM user_role_permissions WHERE permission_id = :p"), {"p": pid})
        conn.execute(sa.text("DELETE FROM user_permissions WHERE id = :p"), {"p": pid})
