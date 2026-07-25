"""Per-company composite uniques + owned company_id NOT NULL (Part C).

Phase 3 of the multi-company isolation migration (PLAN §4.1 "Migration ordering"
step 3; UAC AC-J1 / AC-J2 / AC-K2). The scaffold (302) added nullable
``company_id`` to the 34 owned tables and backfilled every existing row to
Sorento; 303/304 carried it to import jobs + embeddings. This migration makes the
isolation *hard* at the DB:

1. **Composite uniques.** Every owned-table single-column natural-key unique
   (product code, warehouse code, order number, SPO/GRN numbers, brand /
   category / UOM / supplier / transporter / campaign codes+names, ...) is
   dropped and recreated as ``UNIQUE (company_id, <key>)`` so Mocha can import
   its own "CHAIR-01" alongside Sorento's without a unique violation (AC-J2).
   The one nullable natural key (``inbound_shipments.shipment_number``) uses a
   partial index ``WHERE shipment_number IS NOT NULL`` to preserve prior
   multiple-NULL semantics.

   ``customers`` is the exception to "single-column": its natural key is the
   two-column expression unique ``(lower(btrim(customer_code)),
   lower(btrim(customer_name)))`` — raw business strings NOT otherwise scoped by
   an FK, so it is prepended with ``company_id`` too (this is the AutoCount
   masters case AC-J2 targets for debtors). All the OTHER multi-column owned
   uniques (stock (product,warehouse,zone), stock_batches (product,batch),
   spo_allocations (spo_number,product,warehouse), order_lines (order,seq),
   product_suppliers, promotion_products, inbound_shipment_lines,
   product_attachments, customer_contacts one-main, attachments dir+filename)
   are left as-is: every one is already implicitly company-scoped because its
   leading columns are FKs to already-per-company rows, so cross-company
   collision is impossible without adding company_id.

2. **NOT NULL flip (PG only).** Every owned table EXCEPT ``attachments`` (which
   stays nullable — a null company = shared form attachment) gets its
   ``company_id`` re-backfilled to Sorento (idempotent, catches rows created
   during the build window) then ``SET NOT NULL``. The ORM
   ``CompanyScopedMixin.company_id`` stays ``nullable=True`` on purpose so the
   sqlite ``create_all`` used by the test suite stays permissive — the runtime
   auto-stamp + scope filter already prevent null-company writes; PG holds the
   hard constraint. See the note in ``app/models/base.py``.

Revision ID: 305_company_composite_unique
Revises: 304_embedding_company
"""
from alembic import op
from sqlalchemy import inspect as sa_inspect

# Kept <=32 chars: alembic_version.version_num is varchar(32).
revision = "305_company_composite_unique"
down_revision = "304_embedding_company"
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# Single-column natural-key uniques -> composite (company_id, key).
# (table, old_name, new_index_name, key_expr, partial_where_or_None)
#   old_name may be a constraint OR a bare unique index; we drop both forms
#   idempotently. key_expr is the column list AFTER company_id.
_SINGLE_KEY_UNIQUES = [
    ("brands", "brands_brand_code_key", "uq_brands_company_brand_code", "brand_code", None),
    ("brands", "brands_brand_name_key", "uq_brands_company_brand_name", "brand_name", None),
    ("campaign_types", "campaign_types_type_name_key", "uq_campaign_types_company_type_name", "type_name", None),
    ("campaign_types", "uq_campaign_types_type_code", "uq_campaign_types_company_type_code", "type_code", None),
    ("inbound_shipments", "inbound_shipments_shipment_number_key", "uq_inbound_shipments_company_shipment_number", "shipment_number", "shipment_number IS NOT NULL"),
    ("marketing_campaigns", "marketing_campaigns_campaign_code_key", "uq_marketing_campaigns_company_campaign_code", "campaign_code", None),
    ("orders", "orders_order_number_key", "uq_orders_company_order_number", "order_number", None),
    ("picking_headers", "picking_headers_picking_number_key", "uq_picking_headers_company_picking_number", "picking_number", None),
    ("product_categories", "product_categories_category_code_key", "uq_product_categories_company_category_code", "category_code", None),
    ("products", "products_product_code_key", "uq_products_company_product_code", "product_code", None),
    ("purchase_orders", "purchase_orders_po_number_key", "uq_purchase_orders_company_po_number", "po_number", None),
    ("sales_orders", "sales_orders_so_number_key", "uq_sales_orders_company_so_number", "so_number", None),
    ("storage_zones", "storage_zones_zone_code_key", "uq_storage_zones_company_zone_code", "zone_code", None),
    ("suppliers", "suppliers_supplier_code_key", "uq_suppliers_company_supplier_code", "supplier_code", None),
    ("transporters", "uq_transporters_code", "uq_transporters_company_code", "code", None),
    ("transporters", "uq_transporters_normalized_name", "uq_transporters_company_normalized_name", "normalized_name", None),
    ("units_of_measure", "units_of_measure_uom_code_key", "uq_units_of_measure_company_uom_code", "uom_code", None),
    ("warehouses", "warehouses_warehouse_code_key", "uq_warehouses_company_warehouse_code", "warehouse_code", None),
]

# customers: 2-column expression natural key (raw strings, not FK-scoped) ->
# prepend company_id. Handled separately because of the expression form.
_CUSTOMERS_OLD = "uq_customers_code_name_lower"
_CUSTOMERS_NEW = "uq_customers_company_code_name_lower"
_CUSTOMERS_KEY_EXPR = "lower(btrim((customer_code)::text)), lower(btrim((customer_name)::text))"

# Owned tables that flip company_id NOT NULL (all owned EXCEPT attachments).
_NOT_NULL_TABLES = [
    "product_categories", "brands", "units_of_measure", "products", "product_attachments",
    "warehouses", "storage_zones", "stock", "stock_ledger", "stock_batches",
    "promotions", "promotion_groups", "promotion_products", "promotion_attachments",
    "marketing_campaigns", "campaign_types",
    "suppliers", "product_suppliers", "inbound_shipments", "inbound_shipment_lines",
    "spo_allocations", "picking_headers", "picking_lines", "purchase_orders", "purchase_order_lines",
    "customers", "customer_contacts", "transporters", "orders", "order_lines",
    "sales_orders", "sales_order_lines",
    "attachment_directories",
]


def _drop_unique(table: str, name: str) -> None:
    # Idempotently drop whether it was created as a constraint or a bare index.
    op.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{name}"')
    op.execute(f'DROP INDEX IF EXISTS "{name}"')


def upgrade():
    # Some owned tables exist only via ``create_all`` (the legacy commercial ones,
    # e.g. campaign_types / marketing_campaigns), so a given production database may
    # be MISSING a table entirely OR a natural-key column the model has since added
    # (prod campaign_types predates ``type_code``). Guard every operation on the
    # LIVE schema via the inspector so this migration is a no-op for anything absent
    # rather than crashing the whole deploy on a single stale table.
    bind = op.get_bind()
    insp = sa_inspect(bind)
    _tables = set(insp.get_table_names())

    def _columns(table: str) -> set:
        if table not in _tables:
            return set()
        return {c["name"] for c in insp.get_columns(table)}

    # --- 1. Swap single-column natural-key uniques -> (company_id, key) -----------
    for table, old_name, new_name, key_expr, where in _SINGLE_KEY_UNIQUES:
        cols = _columns(table)
        # key_expr is a bare column name here; skip if the table or column is absent
        # on this database, or if company_id was never added to it.
        if "company_id" not in cols or key_expr not in cols:
            continue
        _drop_unique(table, old_name)
        where_clause = f" WHERE {where}" if where else ""
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{new_name}" '
            f"ON {table} (company_id, {key_expr}){where_clause}"
        )

    # customers: expression natural key -> (company_id, lower(code), lower(name))
    _cust_cols = _columns("customers")
    if {"company_id", "customer_code", "customer_name"} <= _cust_cols:
        _drop_unique("customers", _CUSTOMERS_OLD)
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{_CUSTOMERS_NEW}" '
            f"ON customers (company_id, {_CUSTOMERS_KEY_EXPR})"
        )

    # --- 2. Backfill any stragglers + flip company_id NOT NULL (PG only) ----------
    for table in _NOT_NULL_TABLES:
        if "company_id" not in _columns(table):
            continue
        op.execute(
            f"UPDATE {table} SET company_id = '{SORENTO_COMPANY_ID}' "
            f"WHERE company_id IS NULL"
        )
        op.execute(f"ALTER TABLE {table} ALTER COLUMN company_id SET NOT NULL")
    # attachments intentionally stays nullable (null = shared form attachment).


def downgrade():
    # Reverse NOT NULL first so unique rebuilds don't fight constraints.
    for table in _NOT_NULL_TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN company_id DROP NOT NULL")

    # Restore single-column uniques (best-effort, recreated as unique indexes
    # under their original names).
    op.execute(f'DROP INDEX IF EXISTS "{_CUSTOMERS_NEW}"')
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{_CUSTOMERS_OLD}" '
        f"ON customers ({_CUSTOMERS_KEY_EXPR})"
    )

    for table, old_name, new_name, key_expr, where in _SINGLE_KEY_UNIQUES:
        op.execute(f'DROP INDEX IF EXISTS "{new_name}"')
        where_clause = f" WHERE {where}" if where else ""
        op.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS "{old_name}" '
            f"ON {table} ({key_expr}){where_clause}"
        )
