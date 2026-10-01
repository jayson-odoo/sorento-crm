# PLAN: AutoCount SO 'Transferable' flag; non-transferable SOs excluded from Stock Debt

Status: Review (build done, reviewer + browser pass). Track: standard (carries a migration, so not small-fix).
UAC: `so-transferable-acceptance-criteria.md` alongside.

Lane: SO-TRANSFERABLE. Owner ask, 1 Oct 2026: AutoCount sales orders carry a header column
`Transferable` (T/F), e.g. SO421824 F, SO422024 F, SO422049 T, SO422051 T, SO422058 F. Pull it into
sorento-crm; SOs with Transferable = F must NOT be considered in Stock Debt.

## 0. What exists (scouted, PR #1421 comment "STEP 1 scout report")

- AutoCount SOs arrive by ESB push (foundryx-shared-service `SorentoSink`) to
  `POST /api/v1/external/ingest/sales_orders` -> `DocumentIngestService`
  (`app/services/document_ingest_service.py`, `DOCUMENT_SPECS["sales_orders"]`), payload
  `CanonicalSalesOrder` (`app/schemas/canonical_documents.py`). No SO pull lane exists.
- The payload has no Transferable field today; nothing in this repo names it. The shared service
  must start sending it: **ss lane required** (SorentoSink reads `SO.Transferable` and sends
  header `transferable`).
- Stock Debt reads SO demand in `StockDebtService._products` (candidate read) and
  `StockDebtService._demand`. `_demand` is also the fulfilment board's ladder input via
  `project_supply_service.planning_assignments` (R21: one assignment).

## 1. Decisions

- D1 Column `sales_orders.is_transferable BOOLEAN NULL`, no default. NULL = AutoCount never stated
  it (every pre-existing row, every Excel / manual / Order Inquiry SO); treated as transferable.
  Only an explicit FALSE is excluded (`is_transferable IS NOT FALSE`). (Crew decision, 1 Oct 2026.)
- D2 Payload `CanonicalSalesOrder.transferable: Optional[bool]`. Pydantic's bool parsing already
  accepts AutoCount's `T`/`F` (case-insensitive) as well as `true`/`false`; anything else fails
  the record as malformed. Absent or null leaves the stored value untouched (same rule as
  `debtor_code`), so an older ESB build that does not send it never blanks a stated flag.
- D3 AutoCount-owned. Written only by the ingest. Not in `SalesOrderUpdate` (the SO edit PUT
  ignores it), not editable in the UI. Read-back (`POST /external/read/sales_orders`) returns it as
  `transferable`. The DO-OWNERSHIP registry is DO-only (`order_service.py`); an SO has no
  ownership registry and one field does not earn one.
- D4 Stock Debt excludes F in BOTH reads (`_products` and `_demand`), one helper
  `StockDebtService._transferable()`. Owner ruling (b), 1 Oct 2026: F leaves the SHARED
  assignment, so the fulfilment board's ladder (`ProjectSupplyService.planning_assignments`) skips
  F lines too and R21 stays one reader. Consequence: an F order gets no stock reserved anywhere
  until AutoCount flips it to T. F means "not confirmed yet for the queue" (owner).
- D5 Not changed (owner to decide, listed in the scout report): `is_open_demand()` /
  `scm.committed_v` (reorder, netting, coverage, location stock, SPO conversion), outstanding
  report, sales report, chatbot.
- D6 UI (owner ruling, 1 Oct 2026): a Transferable column on the SO list (Yes / No / Not stated
  `Badge`, not sortable) with a Transferable filter (`transferable=yes|no|unknown`), and a
  read-only Transferable field on the SO detail General tab, worded "From AutoCount", the same in
  view and edit. Reuses the existing column, filter and Field components; no mock.

## 2. Slices

1. Migration `sotr_0001_so_is_transferable` (additive, nullable) + model column.
2. Ingest: schema field, `_header_values` fill-when-sent, read-back.
3. Stock Debt exclusion (`_products`, `_demand`).
4. SO list + detail: `is_transferable` on the `SalesOrder` response, list filter, FE column / filter / field.

## 3. Test list (red first)

`sorento_crm_backend/tests/test_so_transferable_ingest.py` (AC-TR-1..5),
`sorento_crm_backend/tests/scm/test_so_transferable.py` (AC-TR-6..9),
`SalesOrdersList.transferable.test.tsx` + `SalesOrderDetail.transferable.test.tsx` (AC-TR-10).
Browser evidence: `evidence/so-transferable/`.

## 4. Follow-ups (not in this lane)

- ss lane: SorentoSink sends header `transferable` (AutoCount `SO.Transferable`). Deploy AFTER this
  PR: `CanonicalSalesOrder` forbids unknown keys, so an early send fails every SO push.
- Owner to decide whether F also leaves `is_open_demand()` / `scm.committed_v` (reorder, netting,
  coverage, location stock, SPO conversion, container requests), the outstanding report, the sales
  report and the chatbot answers built on them.
