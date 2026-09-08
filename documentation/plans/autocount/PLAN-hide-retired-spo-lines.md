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
