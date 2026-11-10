"""PRODUCT-COSTING: dated exchange rates, costing settings, transport rules, party profiles.

Additive only. Six tables (`exchange_rates`, `costing_settings`, `costing_category_rules`,
`costing_product_overrides`, `customer_costing_profiles`, `customer_costing_products`), one
dated `exchange_rates` row per existing `scm.currency_rate` row (the legacy table stays in
place and is no longer read), the `products.party_costing.manage` permission granted by role
slug to `admin` and `director` only, and the `products.cost.view` permission row when no
other lane has made it yet, granted to the same two roles (grants are ON CONFLICT DO NOTHING).

Idempotent (`IF NOT EXISTS`, `WHERE NOT EXISTS`, `ON CONFLICT DO NOTHING`) so the shared dev
database, which converges through `create_all`, can take it in any order. The downgrade drops
exactly what the upgrade added: the tables, the manage permission and its grants, and nothing
of `products.cost.view`.
Contract: documentation/plans/products/CONTRACT-product-costing.md section 2.

Revision ID: pc_0001_product_costing
Revises: combo_0001_part_labels
"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "pc_0001_product_costing"
down_revision = "combo_0001_part_labels"
branch_labels = None
depends_on = None

MANAGE = "products.party_costing.manage"
COST_VIEW = "products.cost.view"
GRANT_ROLES = ("admin", "director")

UPGRADE_SQL = (
    """
    CREATE TABLE IF NOT EXISTS exchange_rates (
        id UUID PRIMARY KEY,
        currency VARCHAR(3) NOT NULL,
        rate_to_base NUMERIC(18, 6) NOT NULL,
        effective_from DATE NOT NULL,
        note VARCHAR(255),
        created_by VARCHAR(100),
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_exchange_rates_currency_from UNIQUE (currency, effective_from),
        CONSTRAINT ck_exchange_rates_rate_positive CHECK (rate_to_base > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS costing_settings (
        id UUID PRIMARY KEY,
        company_id UUID NOT NULL REFERENCES companies(id),
        sst_factor NUMERIC(6, 4) NOT NULL DEFAULT 1.1000,
        default_method VARCHAR(16) NOT NULL DEFAULT 'primary',
        updated_by VARCHAR(100),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_costing_settings_company UNIQUE (company_id),
        CONSTRAINT ck_costing_settings_sst_positive CHECK (sst_factor > 0),
        CONSTRAINT ck_costing_settings_method
            CHECK (default_method IN ('primary', 'average', 'last_po'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS costing_category_rules (
        category_id UUID PRIMARY KEY REFERENCES product_categories(id) ON DELETE CASCADE,
        company_id UUID NOT NULL REFERENCES companies(id),
        mode VARCHAR(8) NOT NULL,
        value NUMERIC(12, 4) NOT NULL,
        updated_by VARCHAR(100),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT ck_costing_category_rules_mode CHECK (mode IN ('add', 'multiply')),
        CONSTRAINT ck_costing_category_rules_value CHECK (value > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS costing_product_overrides (
        product_id UUID PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
        company_id UUID NOT NULL REFERENCES companies(id),
        transport_mode VARCHAR(8),
        transport_value NUMERIC(12, 4),
        cost_method VARCHAR(16),
        cost_method_supplier_id UUID REFERENCES suppliers(id) ON DELETE SET NULL,
        updated_by VARCHAR(100),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT ck_costing_product_overrides_transport CHECK (
            (transport_mode IS NULL AND transport_value IS NULL)
            OR (transport_mode IS NOT NULL AND transport_mode IN ('add', 'multiply')
                AND transport_value IS NOT NULL
                AND transport_value > 0)
        ),
        CONSTRAINT ck_costing_product_overrides_method CHECK (
            cost_method IS NULL OR cost_method IN ('primary', 'selected', 'average', 'last_po')
        ),
        CONSTRAINT ck_costing_product_overrides_supplier CHECK (
            cost_method = 'selected' OR cost_method_supplier_id IS NULL
        )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_costing_profiles (
        customer_id UUID PRIMARY KEY REFERENCES customers(id) ON DELETE CASCADE,
        company_id UUID NOT NULL REFERENCES companies(id),
        markup_pct NUMERIC(7, 3) NOT NULL,
        cost_method VARCHAR(16),
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_by VARCHAR(100),
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT ck_customer_costing_profiles_markup CHECK (markup_pct >= 0),
        CONSTRAINT ck_customer_costing_profiles_method
            CHECK (cost_method IS NULL OR cost_method IN ('primary', 'average', 'last_po'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_costing_products (
        id UUID PRIMARY KEY,
        company_id UUID NOT NULL REFERENCES companies(id),
        customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
        markup_pct NUMERIC(7, 3),
        added_by VARCHAR(100),
        added_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_customer_costing_products_pair UNIQUE (customer_id, product_id),
        CONSTRAINT ck_customer_costing_products_markup
            CHECK (markup_pct IS NULL OR markup_pct >= 0)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_costing_settings_company_id ON costing_settings (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_costing_category_rules_company_id "
    "ON costing_category_rules (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_costing_product_overrides_company_id "
    "ON costing_product_overrides (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_customer_costing_profiles_company_id "
    "ON customer_costing_profiles (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_customer_costing_products_company_id "
    "ON customer_costing_products (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_customer_costing_products_product_id "
    "ON customer_costing_products (product_id)",
)

DROP_TABLES = (
    "customer_costing_products",
    "customer_costing_profiles",
    "costing_product_overrides",
    "costing_category_rules",
    "costing_settings",
    "exchange_rates",
)


def seed_exchange_rates(connection) -> int:
    """One dated `exchange_rates` row per legacy `scm.currency_rate` row: `effective_from` is its
    `as_of`, else today. `ON CONFLICT DO NOTHING`, so a rerun adds nothing. Returns the number of
    rows inserted. The legacy table is read, never changed."""
    legacy = connection.execute(
        sa.text("SELECT COALESCE(to_regclass('scm.currency_rate'), to_regclass('currency_rate'))::text")
    ).scalar()
    if not legacy:
        return 0
    result = connection.execute(
        sa.text(
            f"""
            INSERT INTO exchange_rates
                (id, currency, rate_to_base, effective_from, note, created_by, created_at, updated_at)
            SELECT gen_random_uuid(), upper(btrim(c.currency)), c.rate_to_base,
                   COALESCE(c.as_of, CURRENT_DATE), c.note, 'migration pc_0001', now(), now()
            FROM {legacy} c
            WHERE upper(btrim(c.currency)) <> 'MYR' AND c.rate_to_base > 0
            ON CONFLICT (currency, effective_from) DO NOTHING
            """
        )
    )
    return result.rowcount or 0


def _seed_permissions(conn) -> None:
    now = datetime.utcnow()
    for slug, name, desc in (
        (
            MANAGE,
            "Manage party costing",
            "Edit mark-ups, transport and cost methods on the Costing page, and manage party "
            "costing profiles, products, the SST factor and transport rules.",
        ),
        (
            COST_VIEW,
            "View supplier costs",
            "See supplier costs and the Costing page.",
        ),
    ):
        conn.execute(
            sa.text(
                """
                INSERT INTO user_permissions (id, slug, name, description, created_at)
                SELECT :id, :slug, :name, :desc, :now
                WHERE NOT EXISTS (SELECT 1 FROM user_permissions WHERE slug = :slug)
                """
            ),
            {"id": str(uuid.uuid4()), "slug": slug, "name": name, "desc": desc, "now": now},
        )

    role_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_roles WHERE slug = ANY(:slugs)"), {"slugs": list(GRANT_ROLES)}
        ).fetchall()
    ]
    # Both slugs go to admin and director: the Costing page needs the read gate as well as the
    # manage one, and the grant must not wait on another lane's migration.
    for slug in (MANAGE, COST_VIEW):
        perm_id = conn.execute(sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": slug}).scalar_one()
        for rid in role_ids:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO user_role_permissions (id, role_id, permission_id, assigned_at)
                    VALUES (:id, :r, :p, :now)
                    ON CONFLICT (role_id, permission_id) DO NOTHING
                    """
                ),
                {"id": str(uuid.uuid4()), "r": rid, "p": perm_id, "now": now},
            )


def upgrade() -> None:
    conn = op.get_bind()
    for statement in UPGRADE_SQL:
        conn.execute(sa.text(statement))
    seed_exchange_rates(conn)
    _seed_permissions(conn)


def downgrade() -> None:
    conn = op.get_bind()
    # `products.cost.view` and its grants are NOT removed here, though upgrade() may have inserted
    # or granted them: SUPPLIER-COST-ACCESS (#2319) owns that permission, and a downgrade of this
    # lane must not take a read gate other screens rely on away from anyone.
    perm_ids = [
        r.id
        for r in conn.execute(
            sa.text("SELECT id FROM user_permissions WHERE slug = :s"), {"s": MANAGE}
        ).fetchall()
    ]
    if perm_ids:
        conn.execute(sa.text("DELETE FROM user_role_permissions WHERE permission_id = ANY(:p)"), {"p": perm_ids})
        conn.execute(sa.text("DELETE FROM user_permissions WHERE id = ANY(:p)"), {"p": perm_ids})
    for table in DROP_TABLES:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
