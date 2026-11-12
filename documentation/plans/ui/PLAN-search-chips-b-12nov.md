# PLAN: List search chips, slice 2 (SEARCH-CHIPS B)

Status: Plan. Track: M (no migration expected; to be confirmed by the query-cost check per list), LEAD pattern, cloud lane.
Builds on slice 1 (PR #2367, owner hand test PASS 12 Nov): shared `ListSearchInput` chips mode,
`lib/searchChips.ts`, repeated `query` in `buildDataGridParams` / `parseDetailSearch`, backend
`app/utils/list_search.py` (`search_values`, `search_values_filter`, `SEARCH_VALUES_MATCH`).
Behaviour as accepted in slice 1 (rules 1-8, rule (a) ANY): no new behaviour card.

## Slice 2 scope: the document lists

| List | Frontend | Search param | Backend search clause |
|---|---|---|---|
| Delivery Orders | `order-management/orders/components/OrdersList.tsx:361` | `quick_search` in POST `/api/v1/list-query/search` (`useOrders.ts:64`) | `app/services/order_service.py:1090-1098` (`list_orders` via `list_query_search_service.py:58`); duplicate in `list_query_export_service.py:195-201` |
| Purchase Orders | `scm/purchase-orders/components/PurchaseOrdersList.tsx:542` | `query` (`purchaseOrderService.ts:160`) | `app/services/scm/purchase_order_service.py:852-853` |
| Consignments | `scm/consignments/components/ConsignmentsList.tsx:359` | `query` on `/scm/sales-orders` (`doc_type=consignment`) | already slice 1 (`sales_order_service._search_match`): frontend only |
| Order Inquiries | `project-sales/order-inquiries/components/OrderInquiryHeadersList.tsx:588` | `query` (`orderInquiryService.ts:434`) | `order_inquiry_header_service.py:416-430` or `order_inquiry_worklist_service.py:1689-1761` (to confirm) |
| Proforma Invoices | `scm/proforma-invoices/components/ProformaInvoicesView.tsx:616` | `query` (`proformaInvoiceService.ts:570`) | `app/services/scm/proforma_invoice_service.py:3125-3137` |

Later slices: 3 = Customers, Products and the other master-data lists; 4 = admin / system lists.
Pickers and dialogs keep the plain box.

## Per list

- Backend: read `query` through `search_values` (cap 200 values, 100 characters each), build
  the clause with `search_values_filter` (per-column `ILIKE ANY`), one statement per page.
- Frontend: pass `chips` / `onChipsChange` to `ListSearchInput`, send the values as repeated
  `query` (or the list-query body's list field), restore from `searchQueries`, write the
  address bar like the Sales Orders grid.
- Query cost: EXPLAIN on a prod-size shape for each list's table; a trigram index only where
  the plan shows a seq scan that grows with the number of values (that would turn the lane L).

## Tests

Red first per list: backend repeated-value union, single value unchanged, 100-char cap, 422 over
200; frontend repeated query, chips restored from the URL, address bar written.
