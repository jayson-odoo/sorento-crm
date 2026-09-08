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
