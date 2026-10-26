# PLAN - lines removed in AutoCount release their links (PO, SPO, SO)

Status: PLANNING, 26 Oct 2026. Lane AC-REMOVED-LINES, branch `crew/ac-removed-lines`. Size L
(migration + ingest behaviour + prod reconciliation), lead pattern. Behaviour card filed to the
owner before any code: `ac-removed-lines-behaviour-card.md`. UAC:
`ac-removed-lines-26oct-acceptance-criteria.md` (written after the card's answers).

## 0. What the owner saw (prod, 26 Oct 2026)

PO 202607-S0081, SRTSA-SS line of 546 booked for SO396348: the CRM shows it "Cancelled" with
Placed 546, but the line no longer exists in AutoCount's PODTL. AutoCount moved the qty onto the
document's no-S/O SRTSA-SS line (1,304 on the 20 Oct copy, 1,850 on prod).

Ruling (owner, 26 Oct ~16:25): a line REMOVED (deleted) in AutoCount RELEASES every link the CRM
holds on it, for PO, SO and SPO lines alike. This is distinct from a line CANCELLED in AutoCount
(Cancel PO / Cancel SO documents, `qty_cancelled`, header cancel), which keeps its placement and
shows red "PO cancelled" (LINKAGE-UNIFY Q5). Those paths are left exactly as they are.

## 1. Measured (origin/main bdb54371b1; 20 Oct dev copy `sorento_prod_1020`)

Code (paths under `sorento_crm_backend/app/`):

- PO/SO line sweep: a line the push no longer carries is deleted unless `is_referenced`
  (`services/dependent_probe.py`), else `line_status = cancelled` in place, quantities kept
  (`services/document_ingest_service.py:1639-1657`). Only SO lines flag OI rows
  (`flag_rows_for_cancelled_lines`, `services/project_order_inquiry_service.py:968-1016`: ack
  `acknowledged -> changed`, no link removed, no audit). Every adopted SO line is referenced by
  its mirror (`models/project_so.py:544`), so it is always cancelled in place, never deleted.
- SPO sweep: leftover rows `closed`; AutoCount ref rows also `retired_at`
  (`services/shipping_order_ingest_service.py:557-579`), cleared when restated (:1028). No link
  released.
- No marker on PO/SO lines: `PurchaseOrderLine` (`models/procurement.py:917`) has
  `qty_cancelled` :931, `cancelled_by_cancel_doc` :933, `line_status` :947; `SalesOrderLine`
  (`models/order.py:752`) adds `cancelled_at` :823 (CS Cancel SO board). Alembic head
  `diet_0001_parser_prompt_diet.py`.
- Placed: `services/scm/purchase_order_service.py:499-548` sums OI links filtered only on row
  state; PO detail Status pill `PurchaseOrderDetail.tsx:896-909`, S/O cell :847-859.
- Supply drops the line already: `project_supply_service.py:10079-10081` (open lines only),
  `scm.on_order_v` (`alembic/versions/420_spo_docs_in_allocations.py:788`).
- Links that point at a line: OI links `po_line_id` / `spo_allocation_id`
  (`models/project_so.py:1185/1190`), suggested links (:1296, CASCADE), released links (:1362),
  `scm.order_link_claim` (`models/scm.py:1242-1255`), stock holds `so_line_allocations`
  (`models/project_so.py:1835`), `allocation_claims` (:1895). Evidence, left alone:
  `picking_lines`, `stock_transfers`, `loading_plan_line`, `autocount_cancel_lines`.
- Unlink path: `_remove_links` (`project_order_inquiry_service.py:13556`): note, frees an orphaned
  claim (`services/scm/order_link_service.py:1141`), deletes the link, then `refresh_link_state`
  (:9592) + `_refresh_inquiry_states` (:9527). Retire path for a cancelled SO line:
  `retire_rows_for_cancelled_lines` (:5774): links back, row cancelled, `OI_ROW_CANCELLED`
  audit, purchasing handover email.
- Ingest emits nothing itself; post-commit hooks live in `api/v1/external/ingest.py:356-404`.

Data (20 Oct copy, crew's scale queries rerun): PO 91 removed AutoCount lines, 57 with a live
link (30 OI placements 4,015 qty); SPO 6 retired lines with placements (659); SO 380 removed lines,
73 live OI rows, 2 with placements. Examples and edge cases: the card.

## 2. Design

To be completed after the card's answers.

## 3. Tickets / slices

To be completed after the card's answers.
