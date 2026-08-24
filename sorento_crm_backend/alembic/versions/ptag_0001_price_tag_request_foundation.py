"""price tag request foundation - portal form visibility, request tables, tag templates

S0 of PLAN-price-tag-request. Strictly additive:

1. `contact_access_types.portal_form_types` JSONB column, seeded per access type code.
2. `contact_portal_form_overrides` - per-contact form visibility toggle.
3. `sales_agents.contact_id` FK to respond_contacts.
4. `customers.sales_agent_id` FK to sales_agents.
5. `price_tag_requests` + `price_tag_request_lines` tables.
6. `dealer_kit.tag_templates` table.
7. `dealer_kit.page.kind` + `request_id` columns.
8. Five new permission slugs with grant sweep.

Revision ID: ptag_0001
Revises: portal_rev_0001
Create Date: 2026-08-24
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "ptag_0001"
down_revision = "portal_rev_0001"
branch_labels = None
depends_on = None

SCHEMA = "dealer_kit"

# Permission slugs seeded by this migration.
_PERMS = [
    (
        "dealer_kit.price_tag_requests.view",
        "View Price Tag Requests",
        "View price tag requests submitted via the portal.",
    ),
    (
        "dealer_kit.price_tag_requests.create",
        "Create Price Tag Requests",
        "Create price tag requests (portal contacts, implicit for linked contacts).",
    ),
    (
        "dealer_kit.price_tag_requests.process",
        "Process Price Tag Requests",
        "Claim, design, and manage price tag request lifecycle (CRM marketing).",
    ),
    (
        "dealer_kit.tag_templates.view",
        "View Tag Templates",
        "View tag templates used in the price tag designer.",
    ),
    (
        "dealer_kit.tag_templates.manage",
        "Manage Tag Templates",
        "Create, edit, and delete tag templates for price tag design.",
    ),
]

# Roles that receive all five new slugs.
_GRANT_ALL_ROLES = ("superadmin", "admin")
# Marketing roles receive the full set too - they are the primary operators.
_GRANT_MARKETING_ROLES = ("marketing_manager", "marketing_executive")


def upgrade() -> None:
    # --- 1. portal_form_types on contact_access_types --------------------------
    op.add_column(
        "contact_access_types",
        sa.Column(
            "portal_form_types",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Seed portal_form_types based on access type code patterns.
    # Dealer-type codes get price_tag_request + stock_inquiry.
    # Everything else preserves existing portal behaviour.
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE contact_access_types
            SET portal_form_types = '["price_tag_request", "stock_inquiry"]'::jsonb
            WHERE lower(code) LIKE '%dealer%'
        """)
    )
    conn.execute(
        sa.text("""
            UPDATE contact_access_types
            SET portal_form_types = '["stock_inquiry", "purchase_request", "sponsorship_form", "complaint"]'::jsonb
            WHERE lower(code) NOT LIKE '%dealer%'
              AND portal_form_types = '[]'::jsonb
        """)
    )

    # --- 2. contact_portal_form_overrides table --------------------------------
    op.create_table(
        "contact_portal_form_overrides",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contact_id",
            sa.Text,
            sa.ForeignKey("respond_contacts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("form_type", sa.String(50), nullable=False),
        sa.Column("is_enabled", sa.Boolean, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("contact_id", "form_type", name="uq_contact_portal_form_override"),
    )
    op.create_index(
        "ix_contact_portal_form_overrides_contact_id",
        "contact_portal_form_overrides",
        ["contact_id"],
    )

    # --- 3. sales_agents.contact_id FK -----------------------------------------
    op.add_column(
        "sales_agents",
        sa.Column(
            "contact_id",
            sa.Text(),
            sa.ForeignKey("respond_contacts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sales_agents_contact_id", "sales_agents", ["contact_id"])

    # --- 4. customers.sales_agent_id FK ----------------------------------------
    op.add_column(
        "customers",
        sa.Column(
            "sales_agent_id",
            UUID(as_uuid=False),
            sa.ForeignKey("sales_agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_customers_sales_agent_id", "customers", ["sales_agent_id"])

    # --- 5. price_tag_requests table -------------------------------------------
    op.create_table(
        "price_tag_requests",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "contact_id",
            sa.Text,
            sa.ForeignKey("respond_contacts.id"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),
        sa.Column("debtor_code", sa.String(100), nullable=True),
        sa.Column("debtor_name", sa.String(255), nullable=False),
        sa.Column(
            "promotion_id",
            UUID(as_uuid=False),
            sa.ForeignKey("promotions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("needed_by_date", sa.Date, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
        sa.Column("doc_number", sa.String(30), nullable=False, unique=True),
        sa.Column(
            "page_id",
            UUID(as_uuid=False),
            sa.ForeignKey(f"{SCHEMA}.page.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("portal_draft_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column("po_extraction_result", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
    )
    op.create_index("ix_price_tag_requests_status", "price_tag_requests", ["status"])
    op.create_index("ix_price_tag_requests_contact_id", "price_tag_requests", ["contact_id"])
    op.create_index("ix_price_tag_requests_promotion_id", "price_tag_requests", ["promotion_id"])
    op.create_index("ix_price_tag_requests_company_id", "price_tag_requests", ["company_id"])

    # --- 6. price_tag_request_lines table --------------------------------------
    op.create_table(
        "price_tag_request_lines",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "request_id",
            UUID(as_uuid=False),
            sa.ForeignKey("price_tag_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_type", sa.String(20), nullable=False),
        sa.Column(
            "product_id",
            UUID(as_uuid=False),
            sa.ForeignKey("products.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        # No FK to product_sets yet - table not merged from feat/product-sets.
        sa.Column("product_set_id", UUID(as_uuid=False), nullable=True),
        sa.Column(
            "show_promo_price",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "quantity",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "alternatives",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("included_accessories", sa.Text, nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer,
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("marketing_price_override", sa.Numeric(15, 2), nullable=True),
        sa.Column("marketing_override_reason", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # CHECK: exactly one of product_id / product_set_id must be NOT NULL.
        sa.CheckConstraint(
            "(line_type = 'product' AND product_id IS NOT NULL AND product_set_id IS NULL) "
            "OR (line_type = 'product_set' AND product_set_id IS NOT NULL AND product_id IS NULL)",
            name="ck_price_tag_request_lines_one_ref",
        ),
        sa.UniqueConstraint("request_id", "product_id", name="uq_ptag_line_request_product"),
        sa.UniqueConstraint("request_id", "product_set_id", name="uq_ptag_line_request_set"),
    )
    op.create_index(
        "ix_price_tag_request_lines_request_id",
        "price_tag_request_lines",
        ["request_id"],
    )

    # --- 7. dealer_kit.tag_templates table -------------------------------------
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    op.create_table(
        "tag_template",
        sa.Column(
            "id",
            UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("family", sa.String(50), nullable=False),
        sa.Column("doc", JSONB, nullable=False),
        sa.Column(
            "print_size",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "company_id",
            UUID(as_uuid=False),
            sa.ForeignKey("companies.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", UUID(as_uuid=False), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_tag_template_family",
        "tag_template",
        ["family"],
        schema=SCHEMA,
    )

    # --- 8. dealer_kit.page.kind + request_id ----------------------------------
    op.add_column(
        "page",
        sa.Column(
            "kind",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'catalogue'"),
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "page",
        sa.Column(
            "request_id",
            UUID(as_uuid=False),
            sa.ForeignKey("price_tag_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_dealer_kit_page_request_id",
        "page",
        ["request_id"],
        schema=SCHEMA,
    )

    # --- 9. Permission seeds + grant sweep -------------------------------------
    conn = op.get_bind()
    for slug, name, description in _PERMS:
        perm_id = str(uuid.uuid4())
        conn.execute(
            sa.text("""
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                VALUES (:id, :slug, :name, :desc, now())
                ON CONFLICT (slug) DO NOTHING
            """),
            {"id": perm_id, "slug": slug, "name": name, "desc": description},
        )

    # Grant sweep: give all five slugs to admin-tier and marketing-tier roles.
    all_slugs = [p[0] for p in _PERMS]
    grant_roles = list(_GRANT_ALL_ROLES) + list(_GRANT_MARKETING_ROLES)
    for role_slug in grant_roles:
        # Look up the role id. Skip silently if the role does not exist.
        role_row = conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug = :slug"),
            {"slug": role_slug},
        ).fetchone()
        if not role_row:
            continue
        role_id = role_row[0]
        for perm_slug in all_slugs:
            perm_row = conn.execute(
                sa.text("SELECT id FROM user_permissions WHERE slug = :slug"),
                {"slug": perm_slug},
            ).fetchone()
            if not perm_row:
                continue
            perm_id = perm_row[0]
            conn.execute(
                sa.text("""
                    INSERT INTO user_role_permissions (id, role_id, permission_id)
                    VALUES (:id, :role_id, :perm_id)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                """),
                {"id": str(uuid.uuid4()), "role_id": role_id, "perm_id": perm_id},
            )


def downgrade() -> None:
    # Reverse in the opposite order of upgrade.

    # Drop dealer_kit.page columns
    op.drop_index("ix_dealer_kit_page_request_id", table_name="page", schema=SCHEMA)
    op.drop_column("page", "request_id", schema=SCHEMA)
    op.drop_column("page", "kind", schema=SCHEMA)

    # Drop tag_template table
    op.drop_index("ix_dealer_kit_tag_template_family", table_name="tag_template", schema=SCHEMA)
    op.drop_table("tag_template", schema=SCHEMA)

    # Drop price_tag_request_lines
    op.drop_table("price_tag_request_lines")

    # Drop price_tag_requests
    op.drop_table("price_tag_requests")

    # Drop customers.sales_agent_id
    op.drop_index("ix_customers_sales_agent_id", table_name="customers")
    op.drop_column("customers", "sales_agent_id")

    # Drop sales_agents.contact_id
    op.drop_index("ix_sales_agents_contact_id", table_name="sales_agents")
    op.drop_column("sales_agents", "contact_id")

    # Drop contact_portal_form_overrides
    op.drop_table("contact_portal_form_overrides")

    # Drop contact_access_types.portal_form_types
    op.drop_column("contact_access_types", "portal_form_types")

    # Permission cleanup: remove the five slugs.
    conn = op.get_bind()
    slugs = [p[0] for p in _PERMS]
    for slug in slugs:
        conn.execute(
            sa.text("DELETE FROM user_role_permissions WHERE permission_id IN (SELECT id FROM user_permissions WHERE slug = :slug)"),
            {"slug": slug},
        )
        conn.execute(
            sa.text("DELETE FROM user_permissions WHERE slug = :slug"),
            {"slug": slug},
        )
