"""Import field alias uniqueness moves from one shared triple to per-supplier (owner
ruling A, 24 Sep 2026, review round 2 of `PLAN-import-column-mapper-24sep.md`).

`uq_import_field_alias_triple` (migration 311) is `UNIQUE (doc_type, field, alias)` with
NO `supplier_id` in it, so a SECOND supplier saving the identical (header, field) pair an
earlier supplier already saved loses the `ON CONFLICT DO NOTHING` race against that
supplier's row and never gets one of its own - `for_supplier(B)` then answers nothing for
a header B explicitly mapped (`test_second_supplier_keeps_identical_mapping`, R11).

Split into two partial unique indexes instead of widening the one constraint to include
`supplier_id`, because a NULL `supplier_id` (a SHARED row, answering for every supplier)
must still be unique against every OTHER shared row on its own - `UNIQUE (doc_type,
field, alias, supplier_id)` alone would not do that (Postgres treats NULL as distinct
from NULL for uniqueness purposes, so two shared rows naming the same header would no
longer collide):

  - `uq_import_field_alias_shared` - `(doc_type, field, alias) WHERE supplier_id IS NULL`,
    the exact shape (and name Postgres would have chosen automatically) every existing
    seeder's `ON CONFLICT (doc_type, field, alias) DO NOTHING` already targets. Also the
    exact set migration 311's own plain triple used to police alone.
  - `uq_import_field_alias_supplier` - a PLAIN (non-partial) `(doc_type, field, alias,
    supplier_id)`, the natural arbiter for a supplier-scoped row: a second identical save
    BY THE SAME SUPPLIER still no-ops, a first save by a DIFFERENT supplier now lands its
    own row. Not partial: Postgres only infers a partial index as an `ON CONFLICT` arbiter
    when the statement repeats that index's own predicate verbatim (measured directly -
    42P10 otherwise), and this index's natural conflict target
    (`doc_type, field, alias, supplier_id`) is exactly the one four-column tuple every
    caller already writes. A plain index over the same four columns is harmless for the
    NULL (shared) rows it also covers - Postgres never treats two NULLs as equal, so it
    never fires for them; uniqueness among shared rows is the OTHER index's job.

`app/services/scm/import_mapping_service.py`'s `save()` moves with it: a supplier's insert
targets `uq_import_field_alias_supplier` by column list, and only after confirming no
SHARED row already answers the same way (`test_second_supplier_keeps_identical_mapping`'s
kept half - an identical-to-shared save still writes no redundant supplier row).

Every seeder that runs against a database THIS migration has already reached (four scm
test files, `scripts/bootstrap_env.py`) has its `ON CONFLICT (doc_type, field, alias) DO
NOTHING` narrowed to `... WHERE supplier_id IS NULL DO NOTHING` in the same change - every
one of those inserts a shared (`supplier_id` NULL) row, so the target index changes but
the row shape does not. Every migration under `alembic/versions/` that seeds this table
runs BEFORE this one on a fresh database and is left untouched - the plain triple is still
the correct, currently-live arbiter for their own `upgrade()` at the point they run.

Revision ID: ifa_supplier_uniq
Revises: oirs_0002_reserve_round2
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ifa_supplier_uniq"
down_revision = "oirs_0002_reserve_round2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "ALTER TABLE import_field_alias DROP CONSTRAINT IF EXISTS "
            "uq_import_field_alias_triple"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_import_field_alias_shared "
            "ON import_field_alias (doc_type, field, alias) WHERE supplier_id IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_import_field_alias_supplier "
            "ON import_field_alias (doc_type, field, alias, supplier_id)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_import_field_alias_supplier"))
    bind.execute(sa.text("DROP INDEX IF EXISTS uq_import_field_alias_shared"))
    # The plain triple cannot come back while two SUPPLIER-scoped rows share a
    # (doc_type, field, alias) the split allowed (a second supplier's own row for a
    # header another supplier had already claimed, R11's whole point) - delete the
    # newer duplicate per triple, keep the oldest, before re-adding the constraint.
    bind.execute(
        sa.text(
            """
            DELETE FROM import_field_alias a
            USING import_field_alias b
            WHERE a.supplier_id IS NOT NULL
              AND a.doc_type = b.doc_type AND a.field = b.field AND a.alias = b.alias
              AND a.id <> b.id
              AND (a.created_at, a.id) > (b.created_at, b.id)
            """
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE import_field_alias ADD CONSTRAINT uq_import_field_alias_triple "
            "UNIQUE (doc_type, field, alias)"
        )
    )
