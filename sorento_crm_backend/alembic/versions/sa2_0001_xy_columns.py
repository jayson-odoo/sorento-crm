"""Chatbot stock ask v2 S1 (PLAN-chatbot-stock-ask-v2-24sep.md) - X (chatbot_max_qty)
and Y (chatbot_eta_offset_days) on product_categories and products.

Four nullable INTEGER columns, CHECK >= 0 on all four. No backfill: NULL is the
shipped value and means 0 (R2 - nothing answers until a category opts in). The four
`_crud` permission slugs `master_data.chatbot_stock_limits.{view,add,edit,delete}` are
inserted and `.view` + `.edit` are swept onto every role already holding
`master_data.products.edit`, plus `admin` explicitly (same shape as 522's
`master_data.products.autocount_pull` sweep) - integration roles excluded (an
integration credential importing on a schedule has no browser to set X/Y from).

`ADD COLUMN IF NOT EXISTS` (500_product_exclude_planning's idiom) and the
`DO $$ ... EXCEPTION WHEN duplicate_object` constraint guard (320_company_aware_
routing's idiom) keep this re-runnable against a schema where `Base.metadata.
create_all` already created the ORM-mapped columns - the shape every blank-schema
test fixture in this repo uses.

Revision ID: sa2_0001_xy_columns
Revises: oihr_0003_location_column
Create Date: 2026-09-24
"""
from alembic import op
import sqlalchemy as sa

revision = "sa2_0001_xy_columns"
down_revision = "oihr_0003_location_column"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("product_categories", "chatbot_max_qty", "ck_product_categories_chatbot_max_qty_non_negative"),
    ("product_categories", "chatbot_eta_offset_days", "ck_product_categories_chatbot_eta_offset_days_non_negative"),
    ("products", "chatbot_max_qty", "ck_products_chatbot_max_qty_non_negative"),
    ("products", "chatbot_eta_offset_days", "ck_products_chatbot_eta_offset_days_non_negative"),
)

_PERMISSIONS = [
    (
        "master_data.chatbot_stock_limits.view",
        "View Chatbot Stock Limits",
        "Permission to view Chatbot Stock Limits.",
    ),
    (
        "master_data.chatbot_stock_limits.add",
        "Add Chatbot Stock Limits",
        "Permission to add Chatbot Stock Limits.",
    ),
    (
        "master_data.chatbot_stock_limits.edit",
        "Edit Chatbot Stock Limits",
        "Permission to edit Chatbot Stock Limits.",
    ),
    (
        "master_data.chatbot_stock_limits.delete",
        "Delete Chatbot Stock Limits",
        "Permission to delete Chatbot Stock Limits.",
    ),
]
#: (new slug, sibling slug already granted to the roles that should get it too).
_SWEEP = [
    ("master_data.chatbot_stock_limits.view", "master_data.products.edit"),
    ("master_data.chatbot_stock_limits.edit", "master_data.products.edit"),
]
_GRANT_SLUGS = ("master_data.chatbot_stock_limits.view", "master_data.chatbot_stock_limits.edit")
_GRANT_ROLE_SLUGS = ("admin",)
_EXCLUDED_ROLE_PREFIX = "integration\\_%"


def _add_column(bind, table: str, column: str) -> None:
    bind.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} INTEGER"))


def _add_check(bind, table: str, name: str, column: str) -> None:
    bind.execute(
        sa.text(
            f"""
            DO $$ BEGIN
                ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


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
    for table, column, check_name in _COLUMNS:
        _add_column(bind, table, column)
        _add_check(bind, table, check_name, column)

    for slug, name, description in _PERMISSIONS:
        _insert_permission(bind, slug, name, description)
    for target, source in _SWEEP:
        _sweep(bind, target, source)
    for slug in _GRANT_SLUGS:
        _grant_to_roles(bind, slug, _GRANT_ROLE_SLUGS)


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
    for table, column, check_name in reversed(_COLUMNS):
        bind.execute(sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {check_name}"))
        bind.execute(sa.text(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}"))
