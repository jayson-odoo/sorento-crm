"""Grant `order_management.customers.import` to whoever can already add a customer.

The registry sync creates the permission row at startup, but a permission granted to
nobody is indistinguishable from a broken feature: the Import button would be invisible
for every role, including the master-data staff the importer exists for. So the row is
inserted here (a fresh deploy runs migrations before the app starts) and granted to every
role that already holds `order_management.customers.add` - the same authority, in bulk.

Deliberately its own slug rather than a reused procurement one: an office user who may
upload a debtor listing is not automatically someone who may upload a GRN.

Revision ID: 354_customer_import_permission
Revises: 353_customer_import_aliases
"""
import sqlalchemy as sa
from alembic import op

revision = "354_customer_import_permission"
down_revision = "353_customer_import_aliases"
branch_labels = None
depends_on = None


ADD_SLUG = "order_management.customers.add"
IMPORT_SLUG = "order_management.customers.import"
IMPORT_NAME = "Import Customers"
IMPORT_DESCRIPTION = (
    "Upload a debtor listing to create and update customers for the active company."
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO user_permissions (id, slug, name, description, created_at)
            SELECT gen_random_uuid()::text, :slug, :name, :descr, now()
            WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
            """
        ),
        {"slug": IMPORT_SLUG, "name": IMPORT_NAME, "descr": IMPORT_DESCRIPTION},
    )
    bind.execute(
        sa.text(
            """
            INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
            SELECT gen_random_uuid()::text, rp.role_id, tgt.id, now()
            FROM user_role_permissions rp
            JOIN user_permissions src ON src.id = rp.permission_id AND src.slug = :add
            CROSS JOIN user_permissions tgt
            WHERE tgt.slug = :imp
            ON CONFLICT (role_id, permission_id) DO NOTHING
            """
        ),
        {"add": ADD_SLUG, "imp": IMPORT_SLUG},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM user_role_permissions
            WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :imp)
            """
        ),
        {"imp": IMPORT_SLUG},
    )
    bind.execute(
        sa.text("DELETE FROM user_permissions WHERE slug = :imp"), {"imp": IMPORT_SLUG}
    )
