"""`integration_references.company_id` (BL-056, autocount-brands-ingest D11-D13).

The table (migration 301) mapped an external document to a local record with
NO company column at all: `uq_integration_ref_source` was a GLOBAL unique on
`(source_system, entity_type, source_ref)`, so the same AutoCount DocKey could
never be linked once per company - Mocha (a second AutoCount company) pushing
its own `SORENTO` brand or its own `PO-1` would collide with Sorento's row of
the same key. BL-056 closes that: a `company_id` anchor, scoped uniqueness,
and a `resolve()`/`link()` that read and write within it
(`app/services/integration_reference_service.py`).

**Backfill.** For every company-scoped entity type (`SUPPORTED_ENTITY_TYPES`
minus the one shared type, `sales_agents`), each existing reference's
`company_id` is filled from the row it points at:
`UPDATE integration_references r SET company_id = t.company_id FROM <table> t
WHERE r.entity_type = '<table>' AND r.entity_id = t.id::text AND r.company_id
IS NULL`. `entity_id` is a varchar addressing a `uuid` primary key on every one
of these tables (`app/models/integration_reference.py`), hence the `::text`
cast on the join. Table names are UNQUALIFIED on purpose - `sales_orders` and
`purchase_orders` exist a second time in the `projects` schema, and the bare
name resolves through `search_path` (`public` first on prod, the same rule
`app/services/dependent_probe.py` relies on); qualifying them `public.` would
silently point this migration at the wrong table the day that assumption
stops holding.

A scoped reference still `NULL` after the sweep points at an entity that no
longer exists - exactly the orphan `resolve()` already clears the moment it is
touched (`integration_reference_service.py:224-233`) - so it is deleted here
instead of left pointing at nothing forever. The count removed, per entity
type, is logged at INFO.

**Idempotent.** `ADD COLUMN IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`, and
the backfill's own `WHERE r.company_id IS NULL` means a second run touches
nothing (every scoped row already has one, every orphan is already gone).

Downgrade drops the two partial indexes and the column, then recreates the
global unique - which fails loudly if two companies hold the same
`(source_system, entity_type, source_ref)` by then. That is the correct
outcome: a downgrade that silently deleted one company's claim would lose
data instead of surfacing the incompatibility.

Driven through `apply()`/`revert()` in tests, exactly like
`445_autocount_grant_sweep.py` and `511_brands_esb_grant.py` - the local
Postgres's `alembic_version` is stamped for another branch, so `alembic
upgrade` is not how this one gets checked.

Revision ID: 512_integration_ref_company
Revises: 511_brands_esb_grant
Create Date: 2026-09-12
"""
from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

logger = logging.getLogger(__name__)

revision = "512_integration_ref_company"
down_revision = "511_brands_esb_grant"
branch_labels = None
depends_on = None

# `SUPPORTED_ENTITY_TYPES` minus `sales_agents` (the one shared type) at the
# time this migration was written. Hardcoded rather than imported - a
# migration's behaviour must not drift because the app's allowlist grew a new
# entity type later; a FUTURE scoped type's backfill is that PR's own
# migration, not a retroactive edit of this one.
_COMPANY_SCOPED_ENTITY_TYPES = (
    "products",
    "product_categories",
    "units_of_measure",
    "stock",
    "warehouses",
    "suppliers",
    "customers",
    "sales_orders",
    "purchase_orders",
    "picking_headers",
    "picking_lines",
    "orders",
    "order_lines",
    "brands",
)


def apply(bind) -> None:
    bind.execute(
        sa.text(
            "ALTER TABLE integration_references "
            "ADD COLUMN IF NOT EXISTS company_id UUID REFERENCES companies(id) ON DELETE CASCADE"
        )
    )

    # The backfill, one UPDATE per entity type - unqualified table names (see
    # module docstring).
    for entity_type in _COMPANY_SCOPED_ENTITY_TYPES:
        result = bind.execute(
            sa.text(
                f"""
                UPDATE integration_references r
                SET company_id = t.company_id
                FROM {entity_type} t
                WHERE r.entity_type = :entity_type
                  AND r.entity_id = t.id::text
                  AND r.company_id IS NULL
                """
            ),
            {"entity_type": entity_type},
        )
        if result.rowcount:
            logger.info(
                "integration_ref_company.backfilled entity_type=%s rows=%d",
                entity_type,
                result.rowcount,
            )

    # Orphans: a scoped reference still NULL points at a row that no longer
    # exists (the entity was deleted after the reference was created, before
    # this migration ever ran) - removed rather than left un-scoped forever.
    # Self-verifying (security review): a bare `company_id IS NULL` delete
    # trusts the backfill UPDATE above to have matched every live row - if
    # the unqualified table name ever resolved to the WRONG same-named table
    # (the `projects` schema carries its own `sales_orders`, `purchase_
    # orders` and `brands`), that UPDATE would silently match nothing and
    # this would then delete every reference of that entity type, live rows
    # included. The `NOT EXISTS` re-checks the SAME unqualified name the
    # backfill just joined against, so the delete can only ever remove a row
    # this migration itself has just proven has no matching entity - it
    # cannot compound a wrong-table backfill into data loss.
    for entity_type in _COMPANY_SCOPED_ENTITY_TYPES:
        result = bind.execute(
            sa.text(
                f"""
                DELETE FROM integration_references r
                WHERE r.entity_type = :entity_type
                  AND r.company_id IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM {entity_type} x WHERE x.id::text = r.entity_id
                  )
                """
            ),
            {"entity_type": entity_type},
        )
        if result.rowcount:
            logger.info(
                "integration_ref_company.orphans_removed entity_type=%s rows=%d",
                entity_type,
                result.rowcount,
            )

    bind.execute(
        sa.text(
            "ALTER TABLE integration_references DROP CONSTRAINT IF EXISTS uq_integration_ref_source"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_integration_ref_source_company "
            "ON integration_references (source_system, entity_type, source_ref, company_id) "
            "WHERE company_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_integration_ref_source_shared "
            "ON integration_references (source_system, entity_type, source_ref) "
            "WHERE company_id IS NULL"
        )
    )


def revert(bind) -> None:
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_integration_ref_source_shared"))
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_integration_ref_source_company"))
    bind.execute(sa.text("ALTER TABLE integration_references DROP COLUMN IF EXISTS company_id"))
    # Fails loudly (a genuine unique-violation) if two companies now hold the
    # same (source_system, entity_type, source_ref) - the right outcome for a
    # downgrade, not something to paper over.
    bind.execute(
        sa.text(
            "ALTER TABLE integration_references "
            "ADD CONSTRAINT uq_integration_ref_source UNIQUE (source_system, entity_type, source_ref)"
        )
    )


def upgrade() -> None:
    apply(op.get_bind())


def downgrade() -> None:
    revert(op.get_bind())
