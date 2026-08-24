"""Multi-company: DB-level DEFAULT = Sorento on owned company_id columns.

Rationale
---------
Migration 305 made ``company_id`` NOT NULL on the 33 owned tables (all owned
except ``attachments``, which stays nullable = shared). ORM writes fill
``company_id`` from the request/worker scope (the ``CompanyScopedMixin``
``before_insert`` stamp); a scope-less ORM write to an owned table is *rejected*
before it reaches the DB (AC-D4). But raw ``INSERT`` paths that bypass the ORM
(core/text() inserts in scripts, seeds, and legacy tests) omit ``company_id``
entirely and would hit the NOT NULL constraint.

Sorento is the incumbent/primary company - every pre-isolation row was
backfilled to it (migration 302/305). So an unstamped raw write "belongs to"
Sorento. This migration sets a column DEFAULT of the Sorento company id on the
owned tables, so a raw insert that omits ``company_id`` lands under Sorento
instead of erroring. This does NOT weaken isolation:

* Read filtering is unchanged (the ORM ``do_orm_execute`` filter still applies).
* ORM writes still send an explicit ``company_id`` (scope-stamped: Sorento OR
  Mocha), which overrides the default - a Mocha-scoped create is still Mocha.
* An explicit ``NULL`` still violates NOT NULL (default only fills an *omitted*
  column), so AC-D4's scope-less-ORM-write rejection is untouched.
* ``attachments`` is intentionally excluded (nullable; null = shared form
  attachment).

Mocha (and any future company) data only ever arrives via the scoped ORM /
import path, never via column-omitting raw SQL, so the default is a safety net
for legacy/system writes, not an isolation hole.

Revision ID: 306_company_id_default
Revises: 305_company_composite_unique
"""
from alembic import op
from sqlalchemy import inspect as sa_inspect


revision = "306_company_id_default"
down_revision = "305_company_composite_unique"
branch_labels = None
depends_on = None

SORENTO_COMPANY_ID = "00000000-0000-0000-0000-000000000001"

# Owned tables that are NOT NULL after migration 305 (all owned except
# ``attachments``). Keep in sync with PLAN §4.1.
_OWNED_NOT_NULL_TABLES = (
    "products",
    "product_categories",
    "brands",
    "units_of_measure",
    "product_attachments",
    "warehouses",
    "storage_zones",
    "stock",
    "stock_ledger",
    "stock_batches",
    "promotions",
    "promotion_groups",
    "promotion_products",
    "promotion_attachments",
    "marketing_campaigns",
    "campaign_types",
    "suppliers",
    "product_suppliers",
    "inbound_shipments",
    "inbound_shipment_lines",
    "spo_allocations",
    "picking_headers",
    "picking_lines",
    "purchase_orders",
    "purchase_order_lines",
    "customers",
    "customer_contacts",
    "transporters",
    "orders",
    "order_lines",
    "sales_orders",
    "sales_order_lines",
    "attachment_directories",
)


def upgrade() -> None:
    # Guard on the live schema: some owned tables exist only via ``create_all`` and
    # may be absent (or lack company_id) on a given production database. Skip those
    # rather than crash the deploy (mirrors the guard in migration 305).
    bind = op.get_bind()
    insp = sa_inspect(bind)
    tables = set(insp.get_table_names())
    for table in _OWNED_NOT_NULL_TABLES:
        if table not in tables:
            continue
        if "company_id" not in {c["name"] for c in insp.get_columns(table)}:
            continue
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN company_id SET DEFAULT '{SORENTO_COMPANY_ID}'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    tables = set(insp.get_table_names())
    for table in _OWNED_NOT_NULL_TABLES:
        if table not in tables:
            continue
        if "company_id" not in {c["name"] for c in insp.get_columns(table)}:
            continue
        op.execute(f"ALTER TABLE {table} ALTER COLUMN company_id DROP DEFAULT")
