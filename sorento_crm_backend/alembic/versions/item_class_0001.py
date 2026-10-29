"""ITEM-CLASS: `item_classes` + `products.item_class_id` + `respond_contacts.brand_class_ids`,
and the `master_data.item_classes.*` slugs granted like brands.

Revision ID: item_class_0001
Revises: unpaid_0001_chatbot_ar_role
Create Date: 2026-10-29

AutoCount `Item.ItemClass` (SERENE, DIY; blank on most items) kept on products as reference data,
the `item_types` shape (migration item_type_0001): company-scoped, unique on (company_id, code),
back-created by the products ingest, nullable SET NULL link on `products`.

`respond_contacts.brand_class_ids` JSONB `{brand_id: [item_class_id, ...]}` narrows a brand in
`brand_ids` to those classes (PLAN-item-class-29oct.md D5). NULL everywhere, so no contact's
access changes on deploy.

Grants: every role holding `master_data.brands.<action>` gets `master_data.item_classes.<action>`,
derived in SQL (a new slug reaches no role by itself, migration 298). Permission rows are created
when absent (a database built by alembic alone never ran `sync_permissions`). Additive only, every
statement idempotent; downgrade drops the schema objects and leaves the grants (511 precedent).
"""
import sqlalchemy as sa
from alembic import op

revision = "item_class_0001"
down_revision = "unpaid_0001_chatbot_ar_role"
branch_labels = None
depends_on = None

_ACTIONS = (("view", "View"), ("add", "Add"), ("edit", "Edit"), ("delete", "Delete"))


def apply_grants(bind) -> None:
    for action, verb in _ACTIONS:
        slug = f"master_data.item_classes.{action}"
        bind.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"slug": slug, "name": f"{verb} Item Classes", "descr": f"Permission to {action} Item Classes."},
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                SELECT gen_random_uuid()::text, rp.role_id, target.id, now()
                FROM user_role_permissions rp
                JOIN user_permissions source ON source.id = rp.permission_id AND source.slug = :source
                CROSS JOIN user_permissions target
                WHERE target.slug = :slug
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"source": f"master_data.brands.{action}", "slug": slug},
        )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS item_classes (
            id UUID PRIMARY KEY,
            company_id UUID NOT NULL REFERENCES companies(id),
            item_class_code VARCHAR(50) NOT NULL,
            item_class_name VARCHAR(150) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITHOUT TIME ZONE
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_item_classes_company_id ON item_classes (company_id)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_item_classes_company_item_class_code "
        "ON item_classes (company_id, item_class_code)"
    )
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS item_class_id UUID "
        "REFERENCES item_classes(id) ON DELETE SET NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_item_class_id ON products (item_class_id)")
    op.execute("ALTER TABLE respond_contacts ADD COLUMN IF NOT EXISTS brand_class_ids JSONB")
    apply_grants(op.get_bind())


def downgrade() -> None:
    op.execute("ALTER TABLE respond_contacts DROP COLUMN IF EXISTS brand_class_ids")
    op.execute("DROP INDEX IF EXISTS ix_products_item_class_id")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS item_class_id")
    op.execute("DROP TABLE IF EXISTS item_classes")
