"""Sales module, S6: schema `sales`, `sales.teams`, `sales.team_members`, RBAC, catalog row.

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, 3.7 and 3.8.

1. `CREATE SCHEMA IF NOT EXISTS sales` (owner ruling 26 Sep 06:09, V3; the ADR-0011 precedent):
   the schema is the module key, so the tables carry no `sales_` prefix inside it.
2. `sales.teams` and `sales.team_members` with dated membership (T2): `valid_from` empty means
   "from the beginning" (an agent's first team, V1), one open row per agent per company
   (`uq_sales_team_members_open`), `valid_to >= valid_from`. New tables, so no backfill.
3. `sales.teams.{view,add,edit,delete}`, created when absent and granted to admin and
   superadmin (the grant sweep; everyone else through the role editor).
4. The `sales` row in `app_modules_catalog`, with no `tenant_modules` row: installable but
   dormant, exactly as `scm` and `dealer_kit` shipped. It is switched on in System > App Store.

Downgrade drops the two tables and the catalog row. It leaves the schema (a namespace, never
dropped, ADR-0011) and the permission rows (`sync_permissions` recreates them from the
registry on boot anyway, and a grant an admin made by hand must not vanish with a rollback).

Revision ID: sales_0001_teams
Revises: sb3_company_stock_push_at
Create Date: 2026-09-26
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sales_0001_teams"
down_revision = "sb3_company_stock_push_at"
branch_labels = None
depends_on = None

_PERMS = (
    ("sales.teams.view", "View Sales Teams", "Permission to view Sales Teams."),
    ("sales.teams.add", "Add Sales Teams", "Permission to add Sales Teams."),
    ("sales.teams.edit", "Edit Sales Teams", "Permission to edit Sales Teams."),
    ("sales.teams.delete", "Delete Sales Teams", "Permission to delete Sales Teams."),
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS sales")

    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        schema="sales",
    )
    op.create_index("ix_sales_teams_company_id", "teams", ["company_id"], schema="sales")
    op.create_index(
        "uq_sales_teams_company_lower_name",
        "teams",
        ["company_id", sa.text("lower(name)")],
        unique=True,
        schema="sales",
    )

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "company_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("companies.id"), nullable=False
        ),
        sa.Column(
            "sales_team_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales.teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sales_agent_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("sales_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_to IS NULL OR valid_to >= valid_from",
            name="ck_sales_team_members_dates",
        ),
        schema="sales",
    )
    op.create_index(
        "ix_sales_team_members_company_id", "team_members", ["company_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_team_members_sales_team_id", "team_members", ["sales_team_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_team_members_sales_agent_id", "team_members", ["sales_agent_id"], schema="sales"
    )
    op.create_index(
        "uq_sales_team_members_open",
        "team_members",
        ["company_id", "sales_agent_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        schema="sales",
    )

    bind = op.get_bind()
    for slug, name, description in _PERMS:
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
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, r.id, p.id, now()
            FROM user_roles r
            CROSS JOIN user_permissions p
            WHERE r.slug IN ('admin', 'superadmin') AND p.slug = ANY(:slugs)
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"slugs": [slug for slug, _, _ in _PERMS]},
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO app_modules_catalog
                (id, module_key, display_name, description, sort_order, is_core, dependencies)
            VALUES (:id, 'sales', 'Sales', :desc, :sort, false, CAST(:deps AS jsonb))
            ON CONFLICT (module_key) DO NOTHING
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "desc": "Sales teams, targets with live achievement, opportunities and WhatsApp updates.",
            "sort": "960",
            "deps": '["base", "product", "order"]',
        },
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM tenant_modules WHERE module_key = 'sales'"))
    bind.execute(sa.text("DELETE FROM app_modules_catalog WHERE module_key = 'sales'"))
    op.drop_table("team_members", schema="sales")
    op.drop_table("teams", schema="sales")
