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

Every seeder of this table - every migration under `alembic/versions/` that writes a
shared row here, `scripts/bootstrap_env.py`, and the scm/customer-import test files that
build their world by calling those migrations' own `seed()` functions directly - has its
`ON CONFLICT (doc_type, field, alias) DO NOTHING` narrowed to `... WHERE supplier_id IS
NULL DO NOTHING` in the same change (follow-up commit `fix(alembic): alias seeders target
the shared partial index...`, same day): every one of those inserts a shared (`supplier_id`
NULL) row, so the target index changes but the row shape does not. Adding that predicate is
safe on BOTH schema shapes a `seed()` function can run against - a genuine fresh-DB
`alembic upgrade head`, where the migration in question runs BEFORE this one and the table
still carries only the old plain (non-partial) `uq_import_field_alias_triple` (a predicate
in the `ON CONFLICT` clause is satisfied by a non-partial index trivially, measured
directly), and a database THIS migration has already reached, where the predicate is the
exact partial index's own. Not left unpatched: a test calling e.g. migration 311's
`seed_import_field_aliases()` directly runs it against whichever schema the test's own
database already has, not necessarily in migration order, so "runs before this one on a
fresh DB" does not hold for that call path.

Revision ID: ifa_supplier_uniq
Revises: oirs_0004_reserve_event_zero
Create Date: 2026-09-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ifa_supplier_uniq"
down_revision = "oirs_0004_reserve_event_zero"
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
    # The plain triple cannot come back while two rows share a (doc_type, field, alias)
    # the split allowed. Two passes, in order (review round 3, R17 - the original single
    # pass only ever considered a SUPPLIER row for deletion, and only when it was the
    # NEWER of a same-triple pair, so a supplier row OLDER than a same-triple SHARED row
    # matched neither condition and both survived):
    #
    # 1. A shared row (`supplier_id IS NULL`) already answers for every supplier on this
    #    triple, so it always wins - every supplier row on the same triple is removed
    #    regardless of which is older (unlike pass 2, age does not decide here).
    bind.execute(
        sa.text(
            """
            DELETE FROM import_field_alias a
            WHERE a.supplier_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM import_field_alias b
                  WHERE b.supplier_id IS NULL
                    AND b.doc_type = a.doc_type AND b.field = a.field AND b.alias = a.alias
              )
            """
        )
    )
    # 2. Among what is left (no shared row involved), two different suppliers' own rows
    #    for the same triple - a second supplier's own row for a header another supplier
    #    had already claimed, R11's whole point - keep the oldest, delete the newer.
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
