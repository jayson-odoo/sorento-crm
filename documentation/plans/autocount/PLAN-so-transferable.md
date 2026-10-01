# PLAN: AutoCount SO 'Transferable' flag; non-transferable SOs excluded from Stock Debt

Status: Build (Phase 2, tester-first). Track: standard (carries a migration, so not small-fix).
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
  Only an explicit FALSE is excluded (`is_transferable IS NOT FALSE`). (crew-ask posted; this is
  the recommendation.)
- D2 Payload `CanonicalSalesOrder.transferable: Optional[bool]`. Pydantic's bool parsing already
  accepts AutoCount's `T`/`F` (case-insensitive) as well as `true`/`false`; anything else fails
  the record as malformed. Absent or null leaves the stored value untouched (same rule as
  `debtor_code`), so an older ESB build that does not send it never blanks a stated flag.
- D3 AutoCount-owned. Written only by the ingest. Not in `SalesOrderUpdate` (the SO edit PUT
  ignores it), not editable in the UI. Read-back (`POST /external/read/sales_orders`) returns it as
  `transferable`. The DO-OWNERSHIP registry is DO-only (`order_service.py`); an SO has no
  ownership registry and one field does not earn one.
- D4 Stock Debt excludes F in BOTH reads (`_products` and `_demand`), one helper
  `transferable_demand()` in `stock_debt_service.py`. Because `_demand` is the shared assignment,
  the fulfilment board's ladder drops F lines too (R21: the two must agree on what is free).
  crew-ask posted; if the owner wants the view only, it is a one-flag change.
- D5 Not changed (owner to decide, listed in the scout report): `is_open_demand()` /
  `scm.committed_v` (reorder, netting, coverage, location stock, SPO conversion), outstanding
  report, sales report, chatbot.
- D6 UI: SO detail (`/scm/sales-orders/[id]`) shows a "Not transferable" status `Badge` beside the
  status when `is_transferable === false`; nothing when true or unknown. The list is unchanged.

## 2. Slices

1. Migration `sotr_0001_so_is_transferable` (additive, nullable) + model column.
2. Ingest: schema field, `_header_values` fill-when-sent, read-back.
3. Stock Debt exclusion (`_products`, `_demand`).
4. SO detail: `is_transferable` on `SalesOrder` response + FE badge.

## 3. Test list (red first)

`tests/test_so_transferable_ingest.py`, `tests/scm/test_stock_debt_transferable.py`,
FE vitest for the badge. See UAC for the ids.
