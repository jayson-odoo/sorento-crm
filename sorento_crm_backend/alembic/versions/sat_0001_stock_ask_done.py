"""Sales asks as a to-do list: `stock_asks.done_at` / `done_by`, and the Customer asks permissions.

Plan: documentation/plans/sales/PLAN-sales-asks-todo-29sep.md, 3.1 and 3.4 (one migration for the lane).

1. `done_at TIMESTAMP NULL` (naive UTC, like `created_at`), `done_by_user_id VARCHAR NULL` (FK
   `users.id`) and `done_by_contact_id TEXT NULL` (FK `respond_contacts.id`), both ON DELETE SET
   NULL: who did it is an id, never a name (identity plan 8.3). Added with `IF NOT EXISTS` and a
   guarded ADD CONSTRAINT so the revision is re-runnable.
2. Backfill: a row already `done` reads `done_at = updated_at` (the best answer the table holds),
   both actor ids NULL (shown as "Done", no name). Only rows with no `done_at` yet are touched.
3. `sales.customer_asks.{view,add,edit,delete,view_all}` created when absent, then granted by
   an explicit role list (plan 3.4): `salesperson` gets `view` and `edit` (own list; leading a
   team is the grant for the team's rows, Q7 (c)); `admin`, `superadmin`, `director`,
   `project_sales_manager`, `project_sales_coordinator` and `customer_service` get all five,
   `view_all` included. A role absent on an install is skipped. Integration roles are never
   granted (an integration credential has no browser to clear an ask from), same reasoning as
   `522_autocount_pull_perms`.

Downgrade drops the two columns and leaves the permission rows (`sync_permissions` recreates them
from the registry on boot, and a grant an admin made by hand must not vanish with a rollback).

Revision ID: sat_0001_stock_ask_done
Revises: ideation_status_events_s1
Create Date: 2026-09-29
"""
import sqlalchemy as sa
from alembic import op

revision = "sat_0001_stock_ask_done"
down_revision = "ideation_status_events_s1"
branch_labels = None
depends_on = None

_PERMS = (
    ("sales.customer_asks.view", "View Customer Asks", "Permission to view Customer Asks."),
    ("sales.customer_asks.add", "Add Customer Asks", "Permission to add Customer Asks."),
    ("sales.customer_asks.edit", "Edit Customer Asks", "Permission to edit Customer Asks."),
    ("sales.customer_asks.delete", "Delete Customer Asks", "Permission to delete Customer Asks."),
    (
        "sales.customer_asks.view_all",
        "View All Customer Asks",
        "Permission to view and clear every sales agent's customer asks, not only your own.",
    ),
)
_FKS = (
    ("fk_stock_asks_done_by_user", "done_by_user_id", "users(id)"),
    ("fk_stock_asks_done_by_contact", "done_by_contact_id", "respond_contacts(id)"),
)
#: Explicit role lists (owner check-in 29 Sep 2026: a sweep off `sales.opportunities.view`
#: reached only `admin` on the dev database, so the salesperson role got nothing). A role that
#: does not exist on an install is skipped; nothing is created. Integration roles never appear.
#: Own list only (view + edit): a salesperson sees their own asks; leading a team IS the grant
#: for the team's rows, no slug. Every agent (view + edit + view_all): the office and managers.
_OWN_LIST_ROLE_SLUGS = ("salesperson",)
_ALL_AGENTS_ROLE_SLUGS = (
    "admin",
    "superadmin",
    "director",
    "project_sales_manager",
    "project_sales_coordinator",
    "customer_service",
)
_OWN_LIST_SLUGS = ("sales.customer_asks.view", "sales.customer_asks.edit")


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE stock_asks ADD COLUMN IF NOT EXISTS done_at TIMESTAMP NULL"))
    bind.execute(sa.text("ALTER TABLE stock_asks ADD COLUMN IF NOT EXISTS done_by_user_id VARCHAR NULL"))
    bind.execute(sa.text("ALTER TABLE stock_asks ADD COLUMN IF NOT EXISTS done_by_contact_id TEXT NULL"))
    for name, column, target in _FKS:
        bind.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    -- Scoped to THIS stock_asks: a constraint name is only unique per table.
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = '{name}' AND conrelid = 'stock_asks'::regclass
                    ) THEN
                        ALTER TABLE stock_asks ADD CONSTRAINT {name}
                            FOREIGN KEY ({column}) REFERENCES {target} ON DELETE SET NULL;
                    END IF;
                END $$;
                """
            )
        )
    bind.execute(
        sa.text("UPDATE stock_asks SET done_at = updated_at WHERE state = 'done' AND done_at IS NULL")
    )

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
    grant_sql = sa.text(
        """
        INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
        SELECT gen_random_uuid()::text, r.id, p.id, now()
        FROM user_roles r
        CROSS JOIN user_permissions p
        WHERE r.slug = ANY(:roles) AND p.slug = ANY(:slugs)
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )
    bind.execute(grant_sql, {"roles": list(_OWN_LIST_ROLE_SLUGS), "slugs": list(_OWN_LIST_SLUGS)})
    bind.execute(
        grant_sql,
        {"roles": list(_ALL_AGENTS_ROLE_SLUGS), "slugs": [slug for slug, _, _ in _PERMS]},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TABLE stock_asks DROP COLUMN IF EXISTS done_by_contact_id"))
    bind.execute(sa.text("ALTER TABLE stock_asks DROP COLUMN IF EXISTS done_by_user_id"))
    bind.execute(sa.text("ALTER TABLE stock_asks DROP COLUMN IF EXISTS done_at"))
