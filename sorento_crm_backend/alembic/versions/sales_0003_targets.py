"""Sales module, S1: targets, their periods and product scope; the DO seam; the order date index.

Plan: documentation/plans/sales/PLAN-sales-targets-opportunities-26sep.md, 3.1, 3.2, 3.8, 16.1.

1. `sales.targets` (header: who, what counts, which products, the date range and the optional
   split), `sales.target_periods` (one figure per period, both ends counted) and
   `sales.target_scope` (one category or one product per row). A team target's figure is the
   sum of its agent children (`parent_target_id`, owner ruling 26 Sep 06:09, T3). No
   `commission_method`: S4 adds it with its tiers. New tables, so no backfill.
2. `ix_sales_orders_order_date`: achievement buckets sales orders by `order_date`.
3. The DO seam (R3, V2): `order_lines.sales_order_line_id`, FK `sales_order_lines` ON DELETE SET
   NULL, indexed. Nothing fills it here; the DO integration does. Added with IF NOT EXISTS, so a
   database where the DO lane already added it (or `create_all` built it) is left as it is.
4. `sales.targets.{view,add,edit,delete}`, created when absent and granted to admin and
   superadmin (the `sales_0001_teams` sweep).

Downgrade drops the three tables, the order date index and the DO column with its index. It
keeps the schema (ADR-0011) and the permission rows (S6 precedent).

Revision ID: sales_0003_targets
Revises: sales_0002_team_leader
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "sales_0003_targets"
down_revision = "sales_0002_team_leader"
branch_labels = None
depends_on = None

_PERMS = (
    ("sales.targets.view", "View Sales Targets", "Permission to view Sales Targets."),
    ("sales.targets.add", "Add Sales Targets", "Permission to add Sales Targets."),
    ("sales.targets.edit", "Edit Sales Targets", "Permission to edit Sales Targets."),
    ("sales.targets.delete", "Delete Sales Targets", "Permission to delete Sales Targets."),
)

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "targets",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("target_no", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("subject_kind", sa.String(length=16), nullable=False),
        sa.Column(
            "sales_agent_id",
            _UUID,
            sa.ForeignKey("sales_agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "sales_team_id",
            _UUID,
            sa.ForeignKey("sales.teams.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("metric", sa.String(length=16), nullable=False),
        sa.Column(
            "basis", sa.String(length=16), nullable=False, server_default=sa.text("'ordered'")
        ),
        sa.Column(
            "product_scope", sa.String(length=16), nullable=False, server_default=sa.text("'all'")
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("split_every", sa.SmallInteger(), nullable=True),
        sa.Column("split_unit", sa.String(length=8), nullable=True),
        sa.Column(
            "parent_target_id",
            _UUID,
            sa.ForeignKey("sales.targets.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_by_user_id", _UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "subject_kind IN ('agent', 'team')", name="ck_sales_targets_subject_kind"
        ),
        sa.CheckConstraint(
            "(subject_kind = 'agent' AND sales_agent_id IS NOT NULL AND sales_team_id IS NULL) "
            "OR (subject_kind = 'team' AND sales_team_id IS NOT NULL AND sales_agent_id IS NULL)",
            name="ck_sales_targets_subject",
        ),
        sa.CheckConstraint("metric IN ('amount', 'quantity')", name="ck_sales_targets_metric"),
        sa.CheckConstraint("basis IN ('ordered', 'delivered')", name="ck_sales_targets_basis"),
        sa.CheckConstraint(
            "product_scope IN ('all', 'categories', 'products')",
            name="ck_sales_targets_product_scope",
        ),
        sa.CheckConstraint("end_date >= start_date", name="ck_sales_targets_dates"),
        sa.CheckConstraint(
            "split_every IS NULL OR split_every BETWEEN 1 AND 99",
            name="ck_sales_targets_split_every",
        ),
        sa.CheckConstraint(
            "split_unit IS NULL OR split_unit IN ('day', 'week', 'month')",
            name="ck_sales_targets_split_unit",
        ),
        sa.CheckConstraint(
            "(split_every IS NULL) = (split_unit IS NULL)", name="ck_sales_targets_split_pair"
        ),
        sa.CheckConstraint(
            "parent_target_id IS NULL OR subject_kind = 'agent'",
            name="ck_sales_targets_parent_agent",
        ),
        schema="sales",
    )
    for col in ("company_id", "sales_agent_id", "sales_team_id", "parent_target_id"):
        op.create_index(f"ix_sales_targets_{col}", "targets", [col], schema="sales")
    op.create_index(
        "uq_sales_targets_company_target_no",
        "targets",
        ["company_id", "target_no"],
        unique=True,
        schema="sales",
    )

    op.create_table(
        "target_periods",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "target_id",
            _UUID,
            sa.ForeignKey("sales.targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("target_value", sa.Numeric(15, 2), nullable=False),
        sa.CheckConstraint("period_start <= period_end", name="ck_sales_target_periods_dates"),
        schema="sales",
    )
    op.create_index(
        "ix_sales_target_periods_company_id", "target_periods", ["company_id"], schema="sales"
    )
    op.create_index(
        "uq_sales_target_periods_target_start",
        "target_periods",
        ["target_id", "period_start"],
        unique=True,
        schema="sales",
    )

    op.create_table(
        "target_scope",
        sa.Column("id", _UUID, primary_key=True),
        sa.Column("company_id", _UUID, sa.ForeignKey("companies.id"), nullable=False),
        sa.Column(
            "target_id",
            _UUID,
            sa.ForeignKey("sales.targets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_category_id",
            _UUID,
            sa.ForeignKey("product_categories.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "product_id", _UUID, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=True
        ),
        sa.CheckConstraint(
            "num_nonnulls(product_category_id, product_id) = 1", name="ck_sales_target_scope_one"
        ),
        schema="sales",
    )
    op.create_index(
        "ix_sales_target_scope_company_id", "target_scope", ["company_id"], schema="sales"
    )
    op.create_index(
        "ix_sales_target_scope_target_id", "target_scope", ["target_id"], schema="sales"
    )

    # Core tables, in `public`. IF NOT EXISTS throughout: see the docstring, point 3.
    bind = op.get_bind()
    bind.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_sales_orders_order_date ON sales_orders (order_date)")
    )
    bind.execute(
        sa.text("ALTER TABLE order_lines ADD COLUMN IF NOT EXISTS sales_order_line_id uuid")
    )
    bind.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_order_lines_sales_order_line_id'
                      AND conrelid = 'order_lines'::regclass
                ) THEN
                    ALTER TABLE order_lines
                        ADD CONSTRAINT fk_order_lines_sales_order_line_id
                        FOREIGN KEY (sales_order_line_id) REFERENCES sales_order_lines (id)
                        ON DELETE SET NULL;
                END IF;
            END
            $$
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_order_lines_sales_order_line_id "
            "ON order_lines (sales_order_line_id)"
        )
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


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_table("target_scope", schema="sales")
    op.drop_table("target_periods", schema="sales")
    op.drop_table("targets", schema="sales")
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_sales_orders_order_date"))
    bind.execute(sa.text("DROP INDEX IF EXISTS ix_order_lines_sales_order_line_id"))
    bind.execute(
        sa.text(
            "ALTER TABLE order_lines DROP CONSTRAINT IF EXISTS fk_order_lines_sales_order_line_id"
        )
    )
    bind.execute(sa.text("ALTER TABLE order_lines DROP COLUMN IF EXISTS sales_order_line_id"))
