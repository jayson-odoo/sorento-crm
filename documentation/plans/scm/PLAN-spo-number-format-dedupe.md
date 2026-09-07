# PLAN: SPO number format reconcile + twin-document merge

Status: IN REVIEW (2026-09-07). Slice 1 = merge script. Slice 2 (import match-key) = follow-up, not in this lane.

## Problem (measured on prod export `spo_prod.csv`, 77,270 allocation rows, 7 Sep 2026)

Two spellings of one SPO number live side by side:

| Shape | Rows | Docs | Writer |
| --- | --- | --- | --- |
| `SPO-yyyy/mm-xxxx` | 74,839 | | outstanding/history book upload (`source_system = scm_upload`) |
| `SPO-yyyymm-xxxx` | 2,428 | 230 | CRM conversion (`spo_conversion_service.create`, `document_numbering_rules` doc_type `purchase_order_crm_spo`, `source_system` NULL, `inbound_shipment_id` set) |
| `SPO-20254/12-0074` | 3 | 1 | book upload typo; corrected below |

174 of the 230 CRM docs have a book twin under the slash spelling. Same document, twice:
`purchase_orders` header x2, `purchase_order_lines` x2, `spo_allocations` x2. `scm.on_order_v`
counts both, so planning sees double supply on those 174 SPOs.

Root cause: the upload matches on exact string (`outstanding_import_service._spo_line_plans`
line ~1316 `SPOAllocation.spo_number == number`, and the header lookup ~2160
`getattr(bind.header, bind.number) == number`). `SPO-202608-0090` != `SPO-2026/08-0090`,
so the upload minted a second document. Had the strings matched, the upload would have
SKIPPED the doc as `DOCUMENT_OWNED_ELSEWHERE` (CRM row `source_system` NULL lands in the
`others` bucket).

Already done by the captain on prod, 7 Sep:
- `document_numbering_rules.prefix_template` for `purchase_order_crm_spo` set to
  `SPO-{year}/{month:02d}-`. New CRM SPOs mint the slash spelling. Closes the hole going forward.
- `UPDATE spo_allocations ... regexp_replace` renamed the 56 no-twin CRM docs to slash spelling.
  Their `purchase_orders.po_number` was NOT renamed (still plain).

## Survivor rule

Survivor = the BOOK row (`scm_upload`, slash spelling). Reason: the upload restates only rows it
owns (`source_system == scm_upload`); a CRM-owned survivor would be `owned_elsewhere` on every
future upload and never receive the book's receipt figures again. The CRM row's provenance
(`inbound_shipment_id`, `created_by`, header `source_ref` = shipment id) is carried onto the
survivor, so the shipment link is not lost.

## Deliverable: `sorento_crm_backend/scripts/dedupe_spo_number_format.py`

Operator script, same shape as `scripts/backfill_grn_spo_allocation_links.py` (module docstring
with ROOT CAUSE / WHAT IT DOES / SAFETY, argparse, `--dry-run` DEFAULT, `--apply` to write,
`--spo <number>` repeatable filter, per-doc plan printed, summary at end). Uses `SessionLocal`
from `app.database`. Whole apply run = ONE transaction; any exception rolls back everything.

### Step A: rename plain spellings that have no twin (idempotent)

For each `spo_allocations.spo_number` and `purchase_orders.po_number` matching
`^SPO-(\d{4})(\d{2})-(\d{4})$`, target = `SPO-\1/\2-\3`. If no row in the SAME table + company
already carries the target, rename in place. (Allocation half already ran on prod; the header
half has not. Script must be safe to rerun.)

**Typo shape is separate, and is never merged.** `^SPO-(\d{4})(\d)/(\d{2})-(\d{4})$` (the
`SPO-20254/12-0074` shape) does NOT reuse `\1` for the target year - the stray digit in \2 is
the tell that the whole year got typed wrong, not just the separator. Measured on the one real
instance: its rows carry `issue_date` 2024-12-18, so the true document is `SPO-2024/12-0074`,
NOT `SPO-2025/12-0074` (an unrelated document, issued 2025-12-23, that merely shares the same
trailing `/12-0074`). So the typo's target year is read off the rows' own `issue_date` (every
row of the doc must agree on the year, else the doc is reported and skipped - a disagreement
means the typo guess itself is unsafe to make automatically): target =
`SPO-{issue_year}/{mm}-{xxxx}`. A typo doc is RENAMED only if that target is absent from the
same table + company (Step A's own rule, applied to the corrected target rather than to `\1`);
if the target already exists, the doc is reported as `typo target exists, manual decision` and
left untouched - a typo is evidence the document's own number was mistyped, not evidence it is
the same document as whatever already holds the corrected number, so Step B's twin-merge never
runs on it.

### Step B: merge twins

Twin = a plain-spelling doc P whose target spelling S already exists in the table (the typo
shape never reaches this step - see Step A). Group by `_spo_match_key`
(`procurement_service._spo_match_key`) within company. Process ONE document at a time, in this
order:

1. **Header** (`purchase_orders`). S header survives. For each column in
   `supplier_id, issue_date, expected_date, currency, source_ref`: if S is NULL/empty and P has a
   value, copy. `source_ref` conflict (S = doc type string, P = inbound shipment id): keep S,
   record P value in the backup file. Repoint every FK column in any table that references
   `purchase_orders.id` from P.id to S.id (enumerate FKs at runtime from `pg_constraint`, do
   not hardcode; `purchase_order_lines.purchase_order_id` is handled by step 2, skip it here).
2. **PO lines** (`purchase_order_lines`). Match each P line to an unclaimed S line on the same
   header: pass 1 `(product_id, quantity)` equal, pass 2 `product_id` equal, lowest
   `line_number`/created_at first. Each S line claims at most one P line. Matched: repoint all
   FKs referencing `purchase_order_lines.id` from P line to S line (runtime FK enumeration),
   then delete P line. Unmatched P line: MOVE it (set `purchase_order_id = S.id`, keep its row,
   renumber if a line-number unique key exists). Nothing is dropped.
3. **Allocations** (`spo_allocations`). Match P alloc to unclaimed S alloc under S number:
   pass 1 `(product_id, warehouse_id, allocated_quantity)`, pass 2 `(product_id, warehouse_id)`,
   pass 3 `product_id`; lowest `spo_line_number` first. Matched: copy `inbound_shipment_id`,
   `created_by`, `allocation_notes`, `po_line_id` onto S where S is NULL (po_line_id: map P's
   po line to its S twin from step 2 first); keep S `allocated_quantity` / `quantity_received` /
   `receipt_status` (book is truth) but LOG when they differ from P. Repoint
   `picking_lines.spo_allocation_id`, `order_inquiry_links.spo_allocation_id`,
   `scm_order_link_claims.spo_allocation_id` (again: runtime FK enumeration over
   `spo_allocations.id`, not a hardcoded list) from P.id to S.id, then delete P alloc.
   Unmatched P alloc: MOVE it - set `spo_number` = S number, `spo_line_number` =
   `procurement_service.next_spo_line_number(...)`, keep everything else. Nothing is dropped.
4. `PickingHeaderService(db).sync_received_for_spo_number(S number)` is NOT called at all, by
   any run of this script - not inside the merge transaction, not after it. Measured: the
   method has no `source_system` / already-computed guard - it recomputes `quantity_received`
   from approved GRN picking lines and overwrites whatever the survivor held, which zeroes the
   book's own imported receipt figures (measured on the one real twin: 15 survivor rows go from
   114 received / mixed status to 0 received / `pending`). Nothing this script does touches a
   GRN link or a picking line's `spo_allocation_id` in a way that changes what should be
   received against the survivor - the merge repoints existing FKs and fills NULL columns, it
   never adds or removes a receipt - so there is nothing for a resync to correct, and running
   one would destroy real data instead.
5. Verify before commit: per repointed FK (table, column), the count of rows that pointed at a
   P id before the merge equals the count now pointing at the matching S id, and zero point at
   a P id afterwards (a plain "still references a deleted id" check misses `SET NULL` /
   `CASCADE` FKs entirely - a row that vanished or went NULL passes that check while silently
   losing its link). Zero rows left matching the plain/typo regex, scoped to what this run
   touched. Every S doc's line numbers unique. Any failure raises before the backup JSON's
   own write (see Backup) - the plan file always exists even when a run is rejected.

### Backup

Before `_verify_before_commit` runs (so a rejected run still leaves the plan file - see step 5),
the script writes `<out-dir>/dedupe_spo_<UTC ts>_<hex>.json` holding, per twin: P header row, P
line rows, P alloc rows (full column dump, including a row that was MOVED rather than merged -
its state immediately before the move, e.g. `old_spo_line_number`), the match table (P id -> S
id per table), every FK repoint (table, column, row pk, old, new), and the value conflicts
logged in steps 1-3. Dry run writes the same file with `"dry_run": true`. `<out-dir>` defaults
to `scripts/out/` and is overridable (`--out-dir`), so tests can point it at a throwaway
directory instead of the real one. Reminder printed at start of `--apply`: take
`pg_dump -t purchase_orders -t purchase_order_lines -t spo_allocations` first.

### Tests (Postgres via `tests/_pg_fixture.py`, TDD, red first)

`tests/test_dedupe_spo_number_format.py`, seeding its OWN chain (CI DB is empty):
- plain header+lines+allocs with no twin -> renamed, nothing deleted, rerun is a no-op.
- twin doc with identical line set: P deleted, S carries `inbound_shipment_id`, `created_by`;
  `picking_lines`, `order_inquiry_links`, `scm.order_link_claim` rows point at S ids; none NULL.
- twin doc where P has a product S lacks: that alloc and PO line MOVED under S, not deleted.
- twin where S has more lines than P (48 vs 19 shape): all P matched or moved, and something S
  received from P (a moved line, or a filled NULL column) is actually present on the survivor
  afterwards - not merely that S's own original count is unchanged.
- typo spelling `SPO-20254/12-0074` renames to `SPO-2024/12-0074` (its rows' own `issue_date`
  year, not the `\1` year) when that target is absent; a typo whose corrected target already
  exists is reported (`typo target exists, manual decision`) and left untouched, never merged.
- `--dry-run` writes zero rows (row counts identical before/after) and emits the JSON.
- second `--apply` run finds nothing to do.
- forced failure mid-run, with real prior writes (a fill + an FK repoint already applied before
  the crash on a SECOND delete) - every row is exactly as it was before the run, not merely the
  same row count.
- a run through `main()` (`--apply --spo <n>`) actually commits, and a survivor's
  `quantity_received` / `receipt_status` are unchanged by it (guards B1 - no sync is ever
  called).
- two companies carrying the same malformed number stay two separate documents; a run scoped to
  one company's `--spo` never touches the other's.
- a PO line FK (`scm.loading_plan_line` or `picking_lines.po_line_id`) attached to a matched
  P line lands on the survivor line, not cascaded away with the deleted P line.

UAC 1 (the global "no malformed rows remain" count) is a whole-table invariant meant for a full,
unfiltered `--apply`; it is checked BY HAND after that run, not asserted by the script itself
(which only asserts the rows it touched - see step 5) or by the test suite (which always runs
`--spo`-scoped against the shared, real database).

## Out of scope (follow-up issue)

Import match-key fix in `outstanding_import_service` (`_spo_line_plans` + header lookup) so a
future spelling drift cannot mint twins again. The numbering-rule change already prevents the
known case.
