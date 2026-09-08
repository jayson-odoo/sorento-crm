# PLAN: hide retired SPO allocation lines from the UI

Status: IN PROGRESS 2026-09-08 (user's call). UAC: `hide-retired-spo-lines-acceptance-criteria.md`.
Depends on: PR #740 (D28d `spo_allocations.retired_at`), MERGED a5d4bcac2 2026-09-07T23:16Z.

## 1. Why

SPO-2026/09-0036 shows two C-FHSS14 lines at BRW, 4412 and 3912, and the operator cannot tell
them apart. The 4412 line is a DtlKey AutoCount no longer has: it edited the line after the first
push, so the ingest closed the old row (D3/D11: a leftover is closed, never deleted, because a GRN
line or a claim may point at it) and created the replacement. The row is correct and it is already
out of reorder planning, but the interface shows it as ordinary supply.

Measured on that document: 33 products, 38,777 units genuinely open, 5,393 units across four
retired lines, so the header Total qty reads 44,170. The line grid also disagrees with its own
header, because `get_document` computes the document Balance over outstanding lines only while each
line's own balance is `max(allocated - received, 0)` regardless of status.

User's decision (2026-09-08): hide these rows rather than label them. "AutoCount really don't have
these lines."

## 2. Rules

- **R1 Hide retired, never merely closed.** The hidden set is `retired_at IS NOT NULL`. A line closed
  because it was fully received stays visible: AutoCount has that line, and it is the record of what
  arrived. A cancelled document keeps its current behaviour, out of scope here.
- **R2 A retired line that carries a receipt stays visible.** `quantity_received > 0` means stock
  physically arrived against that line. Hiding it would hide real goods. Under D28c the receipt is
  frozen on retirement, so this case is stable rather than transitional.
- **R3 Hidden means hidden from listings, not from the record.** A GRN, an order-link claim or an
  order-inquiry link that points at a retired row still resolves it and still renders it in its own
  detail view. Only the SPO document lines tab, the SPO allocations grid and the document rollups
  drop it.
- **R4 Rollups follow the same set.** `total_allocated` and `total_received` exclude hidden lines.
  Document Balance already excludes them (outstanding-only) and does not change.
- **R5 Line balance follows line status**, hidden or not: a line that is not outstanding reads
  balance 0, so the grid can never again disagree with its header.
- **R6 One predicate, one place.** `spo_supply` owns the "visible line" clause the way it already
  owns `open_incoming_clauses()`; the detail builder, the grid and the rollups import it.

## 3. Backfill

Rows retired before #740 deploys carry no marker. One-off script, dry-run first, same shape as
`scripts/dedupe_spo_xlsx_superseded.py`: set `retired_at = coalesce(updated_at, now())` where
`source_system = 'autocount'` AND `line_status = 'closed'` AND
`coalesce(receipt_status,'pending') <> 'fully_received'` AND `quantity_received = 0` AND
`retired_at IS NULL`. The receipt and status columns are the only evidence of WHY a row was closed,
and the three conditions together mean "closed without having been received", which is retirement.
Report per document before writing.

## 4. Slices

- S1 [BE] `spo_supply.visible_line_clauses()` + R5 line balance + R4 rollups, with tests.
- S2 [BE] backfill script, dry-run first.
- S3 [FE] nothing to build if the backend stops returning the rows; verify the lines tab, the
  allocations grid and the document header in a browser at 375px and 1280px.
- S4 operate: merge, deploy, run the backfill dry-run, then apply, then re-check SPO-2026/09-0036.

## 5. Decided

The All tab hides retired lines too (user, 2026-09-08: "hide the retired rows everywhere"). A
document's full history stays reachable in the database and through any read that resolves an
allocation by its own id (R3), but no listing offers it.

## 6. Display read sites (measured, `app/services/procurement_service.py`)

| line | reader | what changes |
| --- | --- | --- |
| 1716 | `list_allocations` | the flat grid |
| 1830 | `list_allocations_grouped_by_shipment` | grid grouped by shipment |
| 1970 | `list_allocations_grouped_by_spo_number` | grid grouped by document |
| 2152 | `list_documents` | header rollups, `total_allocated` at 2264 / 2299 |
| 2424 | `get_document` | the lines list and `total_allocated` / `total_received` at 2673 |
| 1129 | per-product allocated total | check whether it is a display or a planning read |

Every planning reader already excludes these rows, because a retired line is closed and
`spo_supply.open_incoming_clauses()` requires open. Only the display readers above show them.

## 7. As-built (S1, coder)

`spo_supply.visible_line_clauses()` added beside `open_incoming_clauses()`:
`or_(SPOAllocation.retired_at.is_(None), func.coalesce(SPOAllocation.quantity_received, 0) > 0)`.
Imported and applied (`from app.services.scm import spo_supply`) at every reader in section 6
except line 1129, decided below:

- `list_allocations` - added to the shared `filters` list (was empty by default, now seeded
  with the visible clause).
- `list_allocations_grouped_by_shipment` - applied twice: to `shipment_filters` (a shipment
  whose only allocations are hidden must not appear as a group of its own) and to
  `allocation_filters` (`matched_spo_allocations_count` counts visible rows only).
- `list_allocations_grouped_by_spo_number` - added to the one shared `filters` list, which
  already fed both the distinct-`spo_number` count/page query and the per-page allocation load.
- `list_documents` - `total_allocated`, `total_received` and `line_count` in the SELECT list
  (originally lines 2264/2265/2274, now shifted) are gated on a new `is_visible` expression
  (`and_(*spo_supply.visible_line_clauses())`) via `CASE WHEN is_visible THEN ... ELSE 0/NULL
  END`; the `sort_map`'s `total_allocated`/`line_count` entries (originally 2299) were updated
  the same way so sorting by either agrees with what is displayed. `has_outstanding`/`balance`/
  `worst_overdue_days`/`earliest_eta` were already computed from `open_incoming_clauses()`
  (line_status-gated), so a retired-closed line was already excluded from them; unchanged.
- `get_document` - the main `rows` query's `.filter(...)` gained
  `*spo_supply.visible_line_clauses()` alongside `SPOAllocation.spo_number == spo_number`. A
  document whose every line is hidden now 404s (`handle_not_found`) the same way a document
  with zero rows always has - no AC exercises this edge, noted here since it is a natural
  consequence of R1 rather than a designed behaviour.

**R5 fix**: `get_document`'s per-line loop computed `balance = max(allocated - received, 0)`
unconditionally, before `outstanding` was even known. Reordered so `outstanding` is computed
first and `balance` is gated on it: `balance = max(allocated - received, 0) if outstanding else
0`. `total_allocated`/`total_received` at the bottom of `get_document` already summed only
over `lines` (now the filtered set) and needed no further change; `balance_sum` already summed
`outstanding_lines` only.

**Step 3 (per-line balance on the grid readers)**: `SPOAllocationResponse` /
`SPOAllocationWithShippedResponse` (used by `list_allocations`,
`list_allocations_grouped_by_shipment`, `list_allocations_grouped_by_spo_number`) carry no
`balance` field at all - only `SPODocumentLine` (used by `get_document`) declares one. R5 is
therefore scoped to `get_document`; nothing to change on the three grid readers because they
never expose a per-line balance to disagree with anything.

**Line 1129 decision (`InboundShipmentService.refresh_shipment_line_statuses`,
`totals_alloc = func.sum(SPOAllocation.allocated_quantity)` grouped by product for one
shipment)**: left UNCHANGED, ruled a planning/reconciliation read, not a display read. It
already applies no `line_status` filter at all today - a fully-received CLOSED line's
allocated quantity counts towards a container's expected total exactly as much as an open
one's, because the figure means "what this container was assigned to carry", a fact fixed at
allocation time, not a live listing of which lines a user currently sees. Excluding a hidden
row here would be a second, different question (which R6 warns against answering twice) and
is not covered by any AC-H test. Residual: a retired, zero-received line that WAS linked to a
shipment before retirement (rare - the ingest never clears `inbound_shipment_id` on retirement)
still inflates that container's `spo_allocated_quantity`, which could hold a physically
complete container at a non-`received` `line_status` forever. Not observed on
SPO-2026/09-0036 (no shipment booked on the retired lines there) and not in scope for this
plan; flagged for a future ticket if it surfaces on real data.

**R3 confirmation (GRN/picking read paths)**: `SPOAllocationService.get_grn` (by GRN id/
picking_number, `joinedload`/`selectinload(PickingLine.spo_allocation)`) and
`list_picking_lines` (a GRN-lines listing, not an SPO-document listing) apply no filter on
`retired_at` and were left untouched - both resolve an allocation via a picking line's own FK,
matching R3 exactly. AC-H5 exercises `get_grn`.

**Backfill script** (`scripts/backfill_retired_spo_lines.py`): modelled on
`dedupe_spo_xlsx_superseded.py`'s shape (`register_company_scope_listeners` +
`company_scope(db, frozenset({company_id}))`, `run(db, company_id, dry_run=True) -> dict`,
`main()` with `--company/--dry-run/--apply`, dry run rolls back, one commit per document, a
per-document report line then a summary). Selection uses `func.coalesce` on
`receipt_status`/`quantity_received` in SQL (not a Python `!=`/`==` filter) because a plain
SQL `!=` against a NULL evaluates to UNKNOWN and silently drops the row instead of including
it - the UAC's own condition is written as `coalesce(...) <> ...` for exactly this reason.
`retired_at = coalesce(updated_at, now())`, done in Python per row since `updated_at` is a
naive `DateTime(timezone=False)` column and `retired_at` is `DateTime(timezone=True)`:
`row.updated_at.replace(tzinfo=timezone.utc)` when set (matching the app's existing
`datetime.utcnow()` writers of `updated_at`), else `datetime.now(timezone.utc)`.

## 8. Round 2 rulings (security review, 2026-09-08)

- **B1.** The backfill's evidence is not "closed and never received", which four writers produce.
  It is "AutoCount replaced this line": a `source_ref` on the row, plus an OPEN sibling in its own
  `(company, spo_number, product_id, upper(location_code))` group created strictly later. A
  cancelled document has no open sibling anywhere, and an absence-closed line has no later sibling,
  so both drop out. Anything that cannot be told apart is left alone: the ingest's own leftover
  sweep stamps it on the next push. The docstring's "exactly two reasons" claim is deleted and the
  four closers are named instead.
- **B2.** A receipt approved after retirement never reached `quantity_received`, because the
  recompute skips a retired row entirely, so R2's guard read a column the retirement path had
  abandoned. A retired `autocount` row is now written from its OWN approved picking lines with the
  D28c floor, `max(stated_received, own approved total)`, and `may_reopen=False`. It still takes no
  share of its group, and AC-X40 still holds because the floor covers a later deletion.

## 9. Round 3 rulings (reviewer, 2026-09-08)

The reviewer measured the old predicate against the lane copy of production: it matched exactly two
rows, both lines of SPO-2023/09-0046, a cancelled document with a single DocKey and no sibling. Its
only effect would have been to make one whole document disappear. Round 2's narrowing stands.

- **B2, the ghost row.** Fixed at the listing end: `list_documents` gates document MEMBERSHIP, not
  only its aggregates, so a document with no visible line does not list. `get_document` keeps its
  404, which is then consistent rather than contradictory: the document has no visible lines, and
  neither surface offers it.
- **S1.** `is_outstanding` in `list_documents` is built from `visible_line_clauses()` as well, so
  Balance, status, worst overdue and earliest ETA cannot count a row the detail page does not
  return. This closes the last structural gap rather than relying on "retired implies closed",
  which no constraint enforces.
- **S2.** `_document_supplier_rollup` counts visible lines only, matching `get_document`.
- **N1 accepted, not deferred.** The packing-list detail's related-SPO strip is a listing and the
  user's decision was every listing, so it takes the clause too.
- **N2.** The backfill keeps `print` for its per-document report: it is an operator-facing report
  like the dedupe script's, not application logging.

## 10. As-built (round 2 + round 3, coder)

**B1** (`scripts/backfill_retired_spo_lines.py`): `_candidate_rows` rewritten. Base predicate is
now `company_id`, `source_system='autocount'`, `line_status='closed'`, `source_ref IS NOT NULL`,
`retired_at IS NULL` (the receipt/`quantity_received` conditions from round 1 are GONE - they were
the wrong evidence, not a second narrowing on top of the right one). A single extra query loads
every OPEN autocount row for the company, indexed by `procurement_service._spo_allocation_group_key`
(imported, not restated) to the latest `created_at` per group; a candidate is eligible only when its
own group key has an entry with `created_at` strictly later than the candidate's own. Docstring
rewritten: the "a line closes for exactly two reasons" claim is gone, replaced by the four closers
(a receipt; the outstanding book's absence sweep; a cancelled document; the deletion service on a
referenced row) and the positive replacement-sibling evidence.

**B2** (`PickingHeaderService._sync_received_for_allocations`, `app/services/procurement_service.py`):
the `if alloc.retired_at is not None: continue` branch now calls
`self._write_received(alloc, max(int(alloc.stated_received or 0), self.compute_received_for_allocation(str(alloc.id))), may_reopen=False)`
before continuing - so a retired row still recomputes off its OWN approved picking lines (never a
group share), floored by whatever was stated for it before retirement, and can never reopen. AC-X40
(`tests/test_spo_xlsx_supersede.py`) still passes unmodified: the floor covers the GRN-delete case
the same way the old "never touched" behaviour did, by different means.

**Round 3, all in `app/services/procurement_service.py` unless noted:**

- `list_documents`: `is_visible` now defined before `is_outstanding` and folded into it
  (`is_outstanding = and_(is_visible, *open_incoming_clauses(), allocated > received)`), so Balance,
  status, worst-overdue and earliest-ETA can never count a hidden row regardless of its own
  `line_status`. A new `visible_line_count_expr` (the same expression `line_count` already computed)
  is shared by the SELECT label, the `sort_map` entry, and a new unconditional
  `rollup.having(visible_line_count_expr > 0)` applied BEFORE the state-specific `having` - a document
  with zero visible lines now drops out of every state (`outstanding`/`completed`/`all`), matching
  `get_document`'s 404 for the same number instead of listing a 0-line row that errors on open.
- `_document_supplier_rollup`: gained `*spo_supply.visible_line_clauses()` in its `.filter(...)`, so
  the majority-supplier tie-break counts the same lines `get_document`'s own `supplier_counts` does.
- `app/api/v1/procurement/packing_lists.py` (`get_packing_list`): both the per-product `totals` query
  (feeds `line.spo_allocated_quantity`) and the `allocations` query (feeds
  `line.related_spo_allocations`, the related-SPO strip) gained `*spo_supply.visible_line_clauses()`.
  A retired line no longer inflates the shipment line's allocated total or appears in the strip.

Verified: `tests/test_spo_xlsx_supersede.py` (53 passed, AC-X40 included), the root-path group and
the `tests/scm/` group from section "verification commands" below both green before and after these
four changes; `tests/test_migration_466_shipment_line_description.py`,
`tests/test_shipment_lines_follow_header_company.py`, `tests/test_consolidated_packing_list.py`,
`tests/test_packing_list_multi_supplier.py` (packing-list detail readers) unaffected.

## 10. Round 4 rulings (security review of the delta, 2026-09-08)

- **Both proposed fixes are taken.** The retired branch gets the same ownership gate its sibling
  has, and the backfill freezes the receipt before stamping. Either alone closes the hole; together
  they make the invariant structural rather than dependent on which writer retired the row.
- **The backfill never stamps a `fully_received` row.** Dropping the receipt predicate let a live
  line that AutoCount still names qualify, if a later open sibling happened to exist. A received
  line is visible under R2 whether marked or not, so the marker buys nothing there and costs the
  row its share of the group's receipt.
- **The packing list is filtered on both halves** (`refresh_shipment_line_statuses`' persisted
  `spo_allocated_quantity` as well as the response), reversing the section 6 note that left it
  alone. The two halves disagreeing inside one payload is worse than either choice, and the user's
  decision was every listing.
