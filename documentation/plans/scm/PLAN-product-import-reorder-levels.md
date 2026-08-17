# PLAN - the product upload carries the reorder level and reorder quantity

Status: drafted 2026-08-16, not started
UAC: `documentation/plans/scm/UAC-product-import-reorder-levels.md`
Branch: `feat/product-import-reorder-levels` (worktree `.claude/worktrees/product-reorder-import`, off `origin/main` @ d331f206b)

## What is already true

- `products.reorder_level` / `products.reorder_quantity` exist (Integer, nullable). Only the
  product form writes them. The product importer reads neither.
- `scm.reorder_level` exists with `level`, `reorder_qty`, `source`, and a doctrine written into
  the model: **a NULL level is not a level of zero** - it means nobody set one, and the engine
  emits the item as `needs_level`.
- `reorder_level_import_service.apply()` already implements the whole reconciliation, including
  the hand-set conflict rule, but it takes **raw file bytes** and parses them itself.
- Migration 347 already seeds header aliases for `Item Code` / `Reorder Level` / `Reorder Qty`
  under doc type `reorder_level`. They were guesses; the sample file matches them exactly.
- `ImportOutcome` counts one entry per `_record` call. Recording a second entry for the same row
  would inflate `successful_rows` and push `processed_rows` past `total_rows`.

**No migration.** Every column this needs is already there.

## Shape

One upload writes two stores. The product importer owns the item-master half and delegates the
planning half to the service that already owns it, rather than restating the conflict rule.

```
Products -> Import (unchanged FE)
        |
        v
bulk_import_products(rows)
        |
        +--> products.reorder_level / .reorder_quantity      (per row, in the existing loop)
        |
        +--> reorder_level_import_service.apply_rows(...)    (once, after the loop)
                     |
                     +--> scm.reorder_level (warehouse_id NULL, source='autocount')
                          honouring the hand-set conflict rule
```

## Steps

### S1 - read the two columns per row (AC-1, AC-2)

`app/services/product_service.py`.

A module-level header map beside the existing `_DISCONTINUED_TRUTHY`, spelled from migration 347
so the two importers cannot drift:

```python
_REORDER_LEVEL_HEADERS = ("reorder_level", "Reorder Level", "Re-order Level", "ReorderLevel", "Min Level")
_REORDER_QTY_HEADERS = ("reorder_quantity", "reorder_qty", "Reorder Qty", "Reorder Quantity", "Re-order Qty", "ReorderQty")
```

One helper, returning a **tri-state** because "absent" and "blank" and "0" are three different
answers and collapsing any two of them is the whole bug this feature can produce:

```python
_ABSENT = object()

def _reorder_cell(row: dict, headers: tuple[str, ...]):
    """`_ABSENT` when no such column on this row, None when blank, else the int."""
```

- A key present with `""` / whitespace -> `None` (blank).
- A key present with a number -> `int(round(float(v)))`. The sample is all integers; a fractional
  value rounds rather than rejecting the row, because a reorder level is a stocking threshold and
  a product row must not fail over one.
- A non-numeric value -> the row is skipped with `INVALID_QUANTITY` and a message naming the cell,
  matching how `Price` already behaves.

### S2 - decide column presence ONCE per file (AC-4)

Before the row loop, scan `products_data` for any row carrying a non-blank value under either
header set:

```python
has_level_col = any(_reorder_cell(r, _REORDER_LEVEL_HEADERS) not in (_ABSENT, None) for r in products_data)
has_qty_col   = any(_reorder_cell(r, _REORDER_QTY_HEADERS)   not in (_ABSENT, None) for r in products_data)
```

`has_level_col` False -> the importer never reads, writes or clears a level, for any row. Same for
quantity, independently.

This is the guard that makes AC-3 safe. The FE's `sheet_to_json` omits blank cells, so per row
"no column" and "blank cell" are the same dict. A file where the column exists but every cell is
blank is therefore indistinguishable from a file with no column, and the importer refuses to act
on it. Deliberate: the alternative is that one such file silently clears every level in the system.

### S3 - write the item master (AC-2, AC-3)

Inside the existing per-row create/update branches, gated on `has_level_col` / `has_qty_col`:

- create: `reorder_level=level` (`None` stays NULL).
- update: `existing.reorder_level = level` unconditionally when the column is present, so a blank
  clears a held value.

Note the contrast with the UOM line four lines above it, which deliberately does NOT overwrite on
a missing value. The difference is ownership: a UOM absent from a file means the file does not
speak about UOM, while a blank cell in a column the file DOES carry is AutoCount stating there is
no level. The file-level guard in S2 is what makes that distinction sound. Comment it at the site.

### S4 - make the SCM service callable with rows, not bytes (AC-5, AC-6)

`app/services/scm/reorder_level_import_service.py`.

Split the parse from the reconciliation. `_resolve` already works off a `LevelReadResult`, so:

```python
def apply(db, data, *, actor=None):            # unchanged signature, unchanged behaviour
    return apply_rows(db, read_workbook(data, db=db), actor=actor)

def apply_rows(db, parsed: LevelReadResult, *, actor=None, product_ids=None): ...
def preview_rows(db, parsed: LevelReadResult, *, product_ids=None): ...
```

`product_ids` lets the product importer pass the `code -> id` map it already built, instead of
`_products_by_code` re-querying 11,649 codes.

**Bulk-prefetch the existing rows.** `_resolve` currently issues one
`db.query(ReorderLevel)...first()` per row. On this file that is 11,649 round trips inside an RQ
job. Replace with a single query keyed on `(product_id, warehouse_id)` for the products in the
batch, into a dict. Fixes the existing SCM upload at the same time; it has the same problem and
has simply never been handed a file this size.

No behaviour change to `apply` / `preview`. Their tests must stay green untouched, which is the
check that this is a refactor.

### S5 - call it from the product import (AC-5, AC-6, AC-7)

At the end of `bulk_import_products`, when `has_level_col`:

- Build `LevelRow(row_number, item_code, reorder_level, location=None, reorder_qty)` for rows whose
  level is **not blank**. Blank rows are omitted, which is what gives AC-7 its asymmetry: the item
  master is cleared, the planning level is left alone.
- `LevelReadResult(rows=..., total_rows=len(rows))` - `ok` is True because `missing_columns` is
  empty.
- `apply_rows(db, parsed, actor=user_id, product_ids=<the map already built>)`, then commit.
- Wrap in try/except and log a warning on failure. This runs AFTER the product rows are committed,
  so it is a post-commit side effect: it must not turn a successful product import into a 500.
  (Same family as `_write_assign_event_log`.)

### S6 - report it (AC-8, AC-9)

One new code in `import_outcome_codes.py`, in the "written, and destructive" section beside
`LINE_CLOSED`, carried on `OUTCOME_UPDATED`: `REORDER_LEVEL_CLEARED`.

**One entry per row, always.** A row that cleared a level keeps its single outcome entry and
changes only its `code`. Recording a second entry would double-count `successful_rows` and drive
`processed_rows` past `total_rows`.

Conflicts do NOT get a per-row code, for a sequencing reason: they are only known after
`apply_rows` runs, which is after the row loop has already recorded its entries. Rather than
restructure the loop into a pre-pass to learn them early, they go into `result.warnings` - a list
the job detail page already renders - naming the item code and both levels. This is also why
`REORDER_LEVEL_CONFLICT` is not a code: nothing would ever carry it.

`finalize` gains `levels_applied` / `levels_cleared` / `level_conflicts` from `outcome.count_of`.

`validate_products_import` (the Test button) appends warning lines - the shared dialog already
renders `warnings` for valid and invalid files alike, so no shared-component edit:

- "N products will get a reorder level from this file."
- "N products will have their reorder level cleared (blank cell in the file)."
- "N reorder levels set by hand will be kept and reported as conflicts."

It must reuse `preview_rows` for the conflict count, or Test and Confirm can disagree about the
same file - the exact thing `preview` exists to prevent on the SCM side.

### S7 - tests

pytest (`sorento_crm_backend/tests/`), on Postgres, seeding its own product / category / UOM chain
with a marker prefix - never borrowing an existing row (CI's database is empty):

- `_reorder_cell` tri-state: absent vs blank vs `0` vs `250` vs `"2.6"` vs `"abc"`.
- AC-2: `0` lands as `0`; blank lands as NULL.
- AC-3: held 250 + blank cell + column present -> NULL.
- AC-4: held 250 + NO column anywhere in the file -> still 250. **The regression that matters.**
- AC-4 boundary: column present but every cell blank -> treated as absent, still 250.
- AC-5: an `scm.reorder_level` row appears with `warehouse_id` NULL and `source='autocount'`.
- AC-6: `source='manual'` + differing level -> level stands, `reorder_qty` lands, one conflict.
- AC-7: blank cell -> product cleared, `scm.reorder_level` untouched.
- AC-9: exactly one outcome entry per row; `processed_rows == total_rows` when a file both clears
  and conflicts.
- S4 refactor: the existing `reorder_level_import_service` tests pass unchanged.

No new vitest: the FE sends the rows it already sends and renders the warnings it already renders.
The only frontend edit is the expected-columns docstring in `productService.ts`, which has no
behaviour to test. Called out rather than quietly skipped.

### S8 - verify against the real file

The sample export is the fixture. Boot the stack (backend, worker, `npm run dev`), upload
`Stock List 14 Aug 2026.xls` at Products → Import through the sidebar with agent-browser, and check:

- Test reports roughly 3,155 levels applied and 642 cleared before anything is written.
- After the run, a product with a positive level shows it on its detail page, one with `0` shows
  `0`, and one with a blank shows nothing.
- `scm.reorder_level` has rows with `warehouse_id IS NULL` and `source='autocount'`.
- Re-upload the same file: `unchanged`, no second set of rows, nothing cleared.
- The job detail page lists the conflicts by item code (seed one hand-set level first).

## Risks

**A partial export wipes levels.** AC-3 is the user's explicit call, and S2's file-level guard is
the only thing standing between it and a filtered export. Worth re-confirming after S8 shows the
Test-button count on a real file: "642 will be cleared" is the number they should sanity-check.

**The two stores can still disagree.** AC-7 means a cleared item-master level leaves the planning
level in place. That is the deliberate trade, but it is a state a person can look at and call a
bug. The job detail message for a clear should say the planning level was left alone.

**`apply_rows` is a refactor of a service with a live caller.** The SCM upload's own tests are the
guard; if they need editing to pass, the refactor changed behaviour and is wrong.
