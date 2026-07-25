"""Multi-company data-isolation scaffold.

Foundation slice (no NOT-NULL flip, no composite-unique swap yet):
- New ``companies`` table + Sorento seed row.
- New M2M grant/membership tables: ``user_companies``, ``respond_contact_companies``.
- ``users.last_active_company_id`` (nullable FK).
- Nullable ``company_id`` (+ index + FK) on all 34 owned business tables.
- Backfill every existing owned row -> Sorento; grant every user {Sorento} +
  last_active = Sorento; membership every respond contact -> {Sorento}.

Attachments are the one owned table kept NULLABLE permanently (null = shared form
attachment). The backfill stamps only *positively-owned* attachments (resource
folder files, product / promotion / packing-list attachments) to Sorento and
leaves form/entity attachments NULL so they remain shared across companies
(AC-G3 / AC-E1). Everything is ``IF NOT EXISTS`` / idempotent.

Deferred to later slices: NOT-NULL flip, composite ``UNIQUE(company_id, key)``,
embedding-row company_id, import-job snapshot, real scope resolver.

Sorento seed company id (fixed, documented): 00000000-0000-0000-0000-000000000001

Revision ID: 302_multi_company
Revises: 301_promo_expiry_rule_engine
"""
from alembic import op

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "302_multi_company"
down_revision = "301_promo_expiry_rule_engine"
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# The 34 owned tables that get a nullable company_id + index + FK.
OWNED_TABLES = [
    # product.py
    "product_categories", "brands", "units_of_measure", "products", "product_attachments",
    # inventory.py
    "warehouses", "storage_zones", "stock", "stock_ledger", "stock_batches",
    # marketing.py
    "promotions", "promotion_groups", "promotion_products", "promotion_attachments",
    "marketing_campaigns", "campaign_types",
    # procurement.py
    "suppliers", "product_suppliers", "inbound_shipments", "inbound_shipment_lines",
    "spo_allocations", "picking_headers", "picking_lines", "purchase_orders", "purchase_order_lines",
    # order.py
    "customers", "customer_contacts", "transporters", "orders", "order_lines",
    "sales_orders", "sales_order_lines",
    # resources.py
    "attachment_directories", "attachments",
]

# attachments backfilled selectively (form attachments stay NULL/shared).
_BACKFILL_ALL = [t for t in OWNED_TABLES if t != "attachments"]


def upgrade():
    # --- 1. companies + M2M tables -------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id uuid PRIMARY KEY,
            name varchar(255) NOT NULL,
            code varchar(50) NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            autocount_ref varchar(255),
            logo_url varchar(500),
            created_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_code ON companies (code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_companies_is_active ON companies (is_active)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_companies (
            id uuid PRIMARY KEY,
            user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_companies_user_id_company_id "
        "ON user_companies (user_id, company_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_companies_user_id ON user_companies (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_companies_company_id ON user_companies (company_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS respond_contact_companies (
            id uuid PRIMARY KEY,
            respond_contact_id text NOT NULL REFERENCES respond_contacts(id) ON DELETE CASCADE,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_at timestamp without time zone NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_respond_contact_companies_contact_company "
        "ON respond_contact_companies (respond_contact_id, company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_contact_companies_contact_id "
        "ON respond_contact_companies (respond_contact_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_respond_contact_companies_company_id "
        "ON respond_contact_companies (company_id)"
    )

    # --- 2. users.last_active_company_id ------------------------------------------
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_company_id uuid")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_users_last_active_company_id'
            ) THEN
                ALTER TABLE users
                    ADD CONSTRAINT fk_users_last_active_company_id
                    FOREIGN KEY (last_active_company_id) REFERENCES companies(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # --- 3. company_id on all 34 owned tables (+ index + FK) -----------------------
    for table in OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS company_id uuid")
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_company_id ON {table} (company_id)"
        )
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_{table}_company_id'
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT fk_{table}_company_id
                        FOREIGN KEY (company_id) REFERENCES companies(id);
                END IF;
            END $$;
            """
        )

    # --- 4. Seed Sorento + backfill -----------------------------------------------
    op.execute(
        f"""
        INSERT INTO companies (id, name, code, is_active, created_at)
        VALUES ('{SORENTO_COMPANY_ID}', 'Sorento', 'SRT', true, now())
        ON CONFLICT (id) DO NOTHING
        """
    )

    # Owned rows (all except attachments) -> Sorento where null.
    for table in _BACKFILL_ALL:
        op.execute(
            f"UPDATE {table} SET company_id = '{SORENTO_COMPANY_ID}' WHERE company_id IS NULL"
        )

    # Attachments: stamp only positively-owned attachments (resource folder files,
    # product / promotion / packing-list attachments). Form/entity attachments stay
    # NULL so they remain shared across companies (AC-G3 / AC-E1).
    op.execute(
        f"""
        UPDATE attachments SET company_id = '{SORENTO_COMPANY_ID}'
        WHERE company_id IS NULL
          AND (
              directory_id IS NOT NULL
              OR id IN (SELECT attachment_id FROM product_attachments)
              OR id IN (SELECT attachment_id FROM promotion_attachments)
              OR id IN (SELECT attachment_id FROM inbound_shipments WHERE attachment_id IS NOT NULL)
          )
        """
    )

    # Every existing user gets the Sorento grant + last_active = Sorento.
    op.execute(
        f"""
        INSERT INTO user_companies (id, user_id, company_id, created_at)
        SELECT gen_random_uuid(), u.id, '{SORENTO_COMPANY_ID}', now()
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM user_companies uc
            WHERE uc.user_id = u.id AND uc.company_id = '{SORENTO_COMPANY_ID}'
        )
        """
    )
    op.execute(
        f"UPDATE users SET last_active_company_id = '{SORENTO_COMPANY_ID}' "
        f"WHERE last_active_company_id IS NULL"
    )

    # Every existing respond contact gets {Sorento} membership.
    op.execute(
        f"""
        INSERT INTO respond_contact_companies (id, respond_contact_id, company_id, created_at)
        SELECT gen_random_uuid(), rc.id, '{SORENTO_COMPANY_ID}', now()
        FROM respond_contacts rc
        WHERE NOT EXISTS (
            SELECT 1 FROM respond_contact_companies rcc
            WHERE rcc.respond_contact_id = rc.id AND rcc.company_id = '{SORENTO_COMPANY_ID}'
        )
        """
    )


def downgrade():
    # Drop company_id (+ FK + index) from owned tables.
    for table in OWNED_TABLES:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_company_id")
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_company_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS company_id")

    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_last_active_company_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_active_company_id")

    op.execute("DROP TABLE IF EXISTS respond_contact_companies")
    op.execute("DROP TABLE IF EXISTS user_companies")
    op.execute("DROP TABLE IF EXISTS companies")
