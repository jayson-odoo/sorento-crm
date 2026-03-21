"""App modules catalog, tenant module state, install events (modular App Store foundation).

Revision ID: 096_app_modules_runtime
Revises: 095_promo_code_access_uniq
Create Date: 2026-03-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "096_app_modules_runtime"
down_revision = "095_promo_code_access_uniq"
branch_labels = None
depends_on = None

_DEFAULT_TENANT = "__default__"

_MODULE_ROWS = [
    ("base", "Base", "System management, user management, integrations foundation.", "000", True),
    ("product", "Product management", "Master data: products, categories, brands, UOM.", "001", False),
    ("resources", "Resource management", "Attachments, directories, attachment types.", "002", False),
    ("inventory", "Inventory management", "Warehouses, stock, batches, ledger.", "003", False),
    ("order", "Order management", "Orders, customers, order lines, tracking import.", "004", False),
    ("procurement", "Procurement management", "Suppliers, GRN, SPO, packing lists, purchase requests.", "005", False),
    ("marketing", "Marketing management", "Promotions, campaigns, promotion attachments.", "006", False),
    ("complaints", "Complaint management", "Complaints and complaint attachments.", "007", False),
    ("sla", "SLA management", "SLA policies, conversation tracking, escalation.", "008", False),
    ("forms", "Forms management", "Dynamic forms, versions, submissions.", "009", False),
    ("notifications", "Notifications", "In-app notifications and delivery.", "010", False),
    ("audit", "Audit", "Audit logs and compliance views.", "011", False),
    ("public_view_links", "Public view links", "Tokenized public pages for shared entities.", "012", False),
]


def upgrade() -> None:
    op.create_table(
        "app_modules_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.String(16), nullable=True),
        sa.Column("is_core", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_app_modules_catalog_module_key", "app_modules_catalog", ["module_key"], unique=True)

    op.create_table(
        "tenant_modules",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("module_key", sa.String(64), sa.ForeignKey("app_modules_catalog.module_key", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_tenant_modules_tenant_id", "tenant_modules", ["tenant_id"])
    op.create_index("uq_tenant_modules_tenant_module", "tenant_modules", ["tenant_id", "module_key"], unique=True)

    op.create_table(
        "module_install_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("module_key", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=True),
        sa.Column("detail", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_module_install_events_tenant_id", "module_install_events", ["tenant_id"])
    op.create_index("ix_module_install_events_module_key", "module_install_events", ["module_key"])

    conn = op.get_bind()
    for mk, dname, desc, sort_o, is_core in _MODULE_ROWS:
        conn.execute(
            sa.text(
                """
                INSERT INTO app_modules_catalog (id, module_key, display_name, description, sort_order, is_core)
                VALUES (gen_random_uuid(), :mk, :dname, :desc, :sort_o, :is_core)
                """
            ),
            {"mk": mk, "dname": dname, "desc": desc, "sort_o": sort_o, "is_core": is_core},
        )

    for mk, _, _, _, _ in _MODULE_ROWS:
        conn.execute(
            sa.text(
                """
                INSERT INTO tenant_modules (id, tenant_id, module_key, enabled)
                VALUES (gen_random_uuid(), :tid, :mk, true)
                """
            ),
            {"tid": _DEFAULT_TENANT, "mk": mk},
        )


def downgrade() -> None:
    op.drop_index("ix_module_install_events_module_key", table_name="module_install_events")
    op.drop_index("ix_module_install_events_tenant_id", table_name="module_install_events")
    op.drop_table("module_install_events")
    op.drop_index("uq_tenant_modules_tenant_module", table_name="tenant_modules")
    op.drop_index("ix_tenant_modules_tenant_id", table_name="tenant_modules")
    op.drop_table("tenant_modules")
    op.drop_index("ix_app_modules_catalog_module_key", table_name="app_modules_catalog")
    op.drop_table("app_modules_catalog")
