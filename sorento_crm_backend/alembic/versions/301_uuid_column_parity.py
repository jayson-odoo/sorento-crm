"""Converge id/reference columns that the models type ``uuid`` but old,
incrementally-migrated databases may still hold as ``varchar``.

Background. Fresh databases are built with ``create_all`` from the models, so
their columns already match the model types. But a long-lived database (prod)
was built by running migrations over time — e.g. ``user_sessions.id`` was created
``sa.String`` by migration 237 — and a later model change (commit 2d0ced269)
retyped 23 columns ``String -> UUID(as_uuid=False)`` WITHOUT a migration, on the
assumption prod was already uuid. That held for 22 columns; ``user_sessions.id``
was still ``varchar`` on prod, so the ORM's ``WHERE id = $1::uuid`` raised
``operator does not exist: character varying = uuid`` on every session write —
auth broke. This migration is the missing conversion, made idempotent so it is a
no-op on the environments that are already uuid (prod after the hotfix, any
create_all build) and only fires on a column still typed ``varchar``.

Each conversion is guarded on the live ``data_type``; every value in these
columns is a uuid string, so ``USING col::uuid`` is safe. FK columns
(orders.billing/shipping_address_id -> customer_addresses.id, stock.zone_id ->
storage_zones.id) drop + re-add their FK around the retype; their referenced PKs
are uuid, so the re-add is type-consistent.

Revision ID: 301_uuid_column_parity
Revises: 300_poly_source_entity_id_uuid
"""
from alembic import op

revision = "301_uuid_column_parity"
down_revision = "300_poly_source_entity_id_uuid"
branch_labels = None
depends_on = None

# (table, column) whose model type is UUID(as_uuid=False) but which an old DB may
# still hold as varchar. FK-free — a plain guarded retype is enough.
_PLAIN: list[tuple[str, str]] = [
    ("attachments", "entity_id"),
    ("attachments", "uploaded_by"),
    ("attachments", "deleted_by"),
    ("audit_logs", "user_id"),
    ("orders", "created_by"),
    ("orders", "updated_by"),
    ("products", "created_by"),
    ("products", "updated_by"),
    ("brands", "created_by"),
    ("customers", "created_by"),
    ("product_categories", "created_by"),
    ("promotions", "created_by"),
    ("marketing_campaigns", "created_by"),
    ("inbound_shipments", "created_by"),
    ("spo_allocations", "created_by"),
    ("picking_headers", "picked_by_user_id"),
    ("picking_headers", "inspected_by_user_id"),
    ("picking_headers", "source_entity_id"),
    ("warehouses", "manager_id"),
    ("user_sessions", "id"),
]

# (table, column, fk_name, ref_table, ref_column) — retype needs the FK dropped
# and re-added (referenced PKs are already uuid).
_FK: list[tuple[str, str, str, str, str]] = [
    ("orders", "billing_address_id", "orders_billing_address_id_fkey", "customer_addresses", "id"),
    ("orders", "shipping_address_id", "orders_shipping_address_id_fkey", "customer_addresses", "id"),
    ("stock", "zone_id", "stock_zone_id_fkey", "storage_zones", "id"),
]


def _guard(table: str, column: str, want: str, body: str) -> str:
    """Run ``body`` only when the live column type differs from ``want``."""
    return f"""
DO $$
BEGIN
  IF (SELECT data_type FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = '{table}' AND column_name = '{column}') = '{want}' THEN
{body}
  END IF;
END $$;
"""


def _plain_convert(table: str, column: str, to_uuid: bool) -> str:
    if to_uuid:
        return _guard(table, column, "character varying",
                      f"    ALTER TABLE {table} ALTER COLUMN {column} TYPE uuid USING {column}::uuid;")
    return _guard(table, column, "uuid",
                  f"    ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar USING {column}::text;")


def _fk_convert(table, column, fk, ref_t, ref_c, to_uuid: bool) -> str:
    if to_uuid:
        return _guard(table, column, "character varying", f"""
    ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {fk};
    ALTER TABLE {table} ALTER COLUMN {column} TYPE uuid USING {column}::uuid;
    ALTER TABLE {table} ADD CONSTRAINT {fk} FOREIGN KEY ({column}) REFERENCES {ref_t}({ref_c});""")
    return _guard(table, column, "uuid", f"""
    ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {fk};
    ALTER TABLE {table} ALTER COLUMN {column} TYPE varchar USING {column}::text;
    ALTER TABLE {table} ADD CONSTRAINT {fk} FOREIGN KEY ({column}) REFERENCES {ref_t}({ref_c});""")


def upgrade():
    for table, column in _PLAIN:
        op.execute(_plain_convert(table, column, to_uuid=True))
    for row in _FK:
        op.execute(_fk_convert(*row, to_uuid=True))


def downgrade():
    for row in _FK:
        op.execute(_fk_convert(*row, to_uuid=False))
    for table, column in _PLAIN:
        op.execute(_plain_convert(table, column, to_uuid=False))
