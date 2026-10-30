# PLAN: Request CS to reserve - tick lines before sending (RESERVE-REQ-PICK, 30 Oct)

Status: planned, small fix track (S: one shared FE dialog + one caller, no backend, no migration,
no auth change). UAC: `reserve-request-pick-acceptance-criteria.md`. Mock:
`documentation/mockups/RESERVE-REQ-PICK/index.html`.

## Journey

Owner on Stock Debt snapshot 26/10 (30 Oct ~09:00): "when user want to request to reserve this OI,
need to give option to remove some lines that they dont want to request to have flexibility".

Today the shared "Request CS to reserve" dialog sends every row it is given and Requested cannot go
below 1, so a row cannot be dropped:

- `sorento_crm_frontend/app/(protected)/project-sales/_shared/components/RequestReserveDialog.tsx:60-62`
  (Requested min 1), `:288-293` (posts `rows.map(...)`, every row), `:169-266` (no tick column).
- OI page picks rows by tick BEFORE the dialog opens:
  `order-inquiries/[id]/components/OrderInquiryDetail.tsx:1056-1066` (`rows={selectedLines}`).
- Snapshot drill passes every requestable frozen row of that OI for the product, no choice:
  `stock-debt/components/SnapshotDrillDialog.tsx:143-174` (`OiRequestDialog`), `:191-199`.

Crew finding: `crew/state/files/stock-debt-reserve-request-30oct.md` point 3 (and point 1 for the
pinned M9713SS row on OI-2609-0676 that the drill offers although its snapshot line reads Short 0).

## Rules

1. The dialog grid gets a leading tick column, the app's standard grid select
   (`components/ui/data-grid-select-column.tsx` `buildSelectColumn`, react-table `rowSelection`),
   header box = tick all / untick all.
2. On open every row is ticked, except rows the caller names as pre-unticked.
3. Only ticked rows are validated and posted. An unticked row's Requested and Location are disabled
   and never block Send.
4. Send (and Park) is disabled when no row is ticked.
5. The dialog header shows "N of M lines" (N ticked, M offered).
6. Snapshot drill only: rows whose frozen snapshot line reads Short 0 (covered or pinned) open
   pre-unticked. Behind ONE constant `PRE_UNTICK_COVERED_LINES` in `SnapshotDrillDialog.tsx`
   (owner decision pending; default on, crew's recommendation) so crew can flip it without a
   behaviour change elsewhere. The OI page passes no pre-unticked rows (its rows are already the
   operator's own ticks).

## Architecture

- Layer: UI only. `RequestReserveDialog` (shared, `_shared/components`) owns the tick state;
  callers only say which rows start unticked (new optional prop `untickedRowIds?: string[]`).
- Shared mechanism reused: `buildSelectColumn` + react-table `enableRowSelection` /
  `state.rowSelection` (same as `OrderInquiryLinesTab.tsx:260`, `SampleRequestsList.tsx:220`).
  No hand-rolled `Set` selection.
- Write path unchanged: hook `useCreateOrderInquiryReserveRequest` -> service -> api-client;
  `POST /order-inquiries/{id}/reserve-requests` already takes any subset of rows
  (`order_inquiry_reserve_service.py`). No backend change.
- Class of fix: the selection rule lives in the one shared dialog, so both entry points (OI page,
  snapshot drill) get it from one place.

## Tests (red first)

`_shared/components/RequestReserveDialog.pick.test.tsx` (vitest):
- every row ticked on open, header reads "2 of 2 lines";
- untick one row: header "1 of 2 lines", Send posts only the ticked row;
- untick all: Send disabled; header tick box re-ticks all;
- an unticked row with an invalid Requested does not block Send;
- `untickedRowIds` opens those rows unticked.

`stock-debt/components/SnapshotClient.drill.test.tsx` (extend): from the drill, a frozen row whose
line reads Short 0 opens unticked; one with Short > 0 opens ticked.

## Out of scope

- The 95 legacy OI rows linked to the wrong SO line (finding point 1) - data fix, not code.
- After-snapshot OIs requestable from the drill (finding point 2) - by design.
