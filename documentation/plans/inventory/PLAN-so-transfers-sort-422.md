# PLAN: SO page Transfers tab sends the SO list's sort (422 toast)

**Status:** in review, PR #1857, reviewer READY (small fix track: FE one-line guard + tests, no migration, no auth change)
**Lane:** SO-TRANSFERS-SORT-422, branch `crew/so-transfers-sort-422`
**UAC:** `so-transfers-sort-422-acceptance-criteria.md` (alongside)

## Report

Owner on PROD, 25 Oct 2026: Sales Orders > SO273125 > Delivery/Transfers, red toast
"sort: Input should be 'transfer_no', 'state', 'kind', 'qty', 'item_code', 'from_location',
'to_location', 'so_number' or 'proposed_at'".

## Cause (read from the code)

- The BE list route refuses any sort outside `TransferSort`
  (`sorento_crm_backend/app/api/v1/inventory/stock_transfers.py:55`, used at `:107`). Correct,
  stays strict.
- The SO list carries its own list state into the detail URL for the prev/next pager
  (`sorento_crm_frontend/app/(protected)/scm/sales-orders/components/SalesOrdersGrid.tsx:405`;
  default sort `order_date`, `:197`). So the SO detail URL reads
  `/scm/sales-orders/<id>?page=1&limit=..&sort=order_date&dir=desc&...`.
- The SO detail page embeds the Transfers grid pinned to the order
  (`.../scm/sales-orders/[id]/components/SalesOrderDetail.tsx:2328`).
- `StockTransfersPanel` restores its state from the page URL unconditionally
  (`.../inventory-management/stock-transfers/components/StockTransfersPanel.tsx:171`,
  `useListStateFromUrl`). Embedded, that URL belongs to the HOST page, so the panel adopts the
  SO list's `sort=order_date` (and its page, limit and search text) and sends them to the
  transfers list: 422. Same on the sales-agent detail page
  (`.../sales-agents/[id]/components/SalesAgentDetail.tsx:486`).

Column ids are not the cause: every sortable column id in the panel (`transfer_no`, `item_code`,
`kind`, `so_number`, `state`, `proposed_at`) is in the BE Literal.

## Fix

A panel pinned to a record (`salesOrderId` or `salesAgentId` set) does not own the page URL, so
it does not restore from it: `useListStateFromUrl(..., { enabled: !pinned })`. The standalone
Transfers page (no pin) keeps the Back-restores-state behaviour.

## Other SO-page tabs checked

- Lines, Delivery, General: no list-state URL read. `SalesOrderDetail.tsx` reads
  `useSearchParams` for the consignment redirect (`:504`), `edit` (`:636`) and `tab` / `line`
  (`:671-683`); none of them feeds a list request.
- Invoices (`SalesOrderInvoices`): no `useSearchParams` / `useListStateFromUrl`.
- So the Transfers tab is the only SO-page tab with the mismatch.

Out of scope, noted for follow-ups:

- `SalesOrdersGrid` embedded on the sales-agent detail page (`SalesAgentDetail.tsx:475`)
  restores page + search (not sort) from the agent page URL. No 422 (it does not take the
  sort), but it can open on the wrong page.
- Pre-existing: Back from a transfer opened on the SO tab lands on the standalone Transfers
  page showing every transfer, not that order's. The URL keeps `sales_order_id`, but the
  restore callback has no setter for it or `sales_agent_id` (`StockTransfersPanel.tsx:182-191`).

## Tests

- FE vitest (red first): `StockTransfersPanel.test.tsx`, pinned to a sales order / sales agent
  with the host's list state in the URL, the panel asks for `proposed_at desc`, page 1, no
  search; the standalone restore test stays green.
- BE route test (guard): the SO-pinned list sorts by every column the panel offers (200) and
  refuses the SO list's `order_date` (422), so the BE stays strict.
