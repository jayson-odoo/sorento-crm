"""Customer Service reaches Fulfilment Planning (DEALER-PLANNING R16, owner Q2 (a), 1 Nov 2026)

Revision ID: dp_0001_cs_planning_access
Revises: akn_0001_knowledge
Create Date: 2026-11-01 15:00:00.000000

Dealer CS plans dealer sales orders on Fulfilment Planning, whose list and board read
`projects.projects.view` and whose decisions write `projects.projects.edit`, and they open it
from the SCM side on `scm.dashboard.view`. Pipeline and forecasts become visible to the role,
which the owner accepted.

Additive and idempotent: a grant the role already holds is left alone, and a database without
the role or a slug grants what it can and raises nothing. No other role moves.

The downgrade removes nothing: a grant this migration made cannot be told apart from one an
admin made before it, and taking an admin's grant away is worse than leaving this one.
"""
import sqlalchemy as sa
from alembic import op

revision = "dp_0001_cs_planning_access"
down_revision = "akn_0001_knowledge"
branch_labels = None
depends_on = None

ROLE = "customer_service"
SLUGS = ("projects.projects.view", "projects.projects.edit", "scm.dashboard.view")


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid(), r.id, p.id, now()
            FROM user_roles r
            JOIN user_permissions p ON p.slug = ANY(:slugs)
            WHERE r.slug = :role
              AND NOT EXISTS (
                  SELECT 1 FROM user_role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        ),
        {"role": ROLE, "slugs": list(SLUGS)},
    )


def downgrade() -> None:
    pass
