# PLAN: List search chips (SEARCH-CHIPS)

Status: Build (round 2). Mock v1 approved, rule (a) ANY; crew ruling 12 Nov: trigram indexes + clause rewrite.
Track: L (was M; one index migration added by crew ruling), LEAD pattern, cloud lane. No auth/RBAC change.

Owner, 12 Nov: type a value, press Enter, it becomes a chip in the search box; keep typing and
pressing Enter to add more; the list shows the result for all chips together. Cases: several sales
order numbers in one search; a sales order number together with a customer.

## What exists today (measured)

- One shared box: `sorento_crm_frontend/components/common/ListSearchInput.tsx:53`, one string
  `value`, Enter only calls an optional `onSubmit`. Debounce: `hooks/useDebouncedSearch.ts:42`
  (200 ms, trims). 176 non-test files render `<ListSearchInput` (lists, pickers, dialogs).
- Sales Order list: `app/(protected)/scm/sales-orders/components/SalesOrdersGrid.tsx:1043-1053`,
  placeholder "Search SO, customer, product or agent...", box `w-64`.
- Sent as ONE `query=` param by `lib/api-client.ts:229` (`buildDataGridParams`).
- Backend: `GET /api/v1/scm/sales-orders`, `query: Optional[str]`
  (`sorento_crm_backend/app/api/v1/scm/sales_orders.py:83`); the match is
  `SalesOrderService.list` (`app/services/scm/sales_order_service.py:1545-1593`): substring ILIKE on
  so_number, debtor_name, customer.customer_name, project_label, po_ref, folded po_ref_key, plus
  EXISTS on a line's product code/name and EXISTS on the agent code/person.
- Search memory: search text is NOT in the per-user view memory (AC-D1/D2,
  `SalesOrdersGrid.tsx:283`). It reaches the address bar when a row is opened
  (`components/ui/data-grid-table.tsx:680-695`) and comes back on Back / prev-next via
  `useListStateFromUrl` -> `parseDetailSearch` (`lib/listNavQuery.ts:83`, reads ONE `query`).
  A page refresh before opening a row loses it today.
- Export on Sales Orders is the toolbar's selected-rows export (`exportConfig` without
  `kind: 'listQuery'`, `SalesOrdersGrid.tsx:1218`); Sales Orders has no "Select all N" banner
  (`selectAllMatching` not passed). Both follow whatever rows the list shows.
- Shared Enter-to-chip precedent: `components/common/StringChipInput.tsx` (2 admin modals).
  Chip look: `SearchableMultiSelect.tsx:404-426`.
- Repeated free-text params already have a parser: `app/utils/multi_value.py` `multi_text`
  (never splits on commas, dedupes, caps at 200).
- Open PR #2362 (LIST-FILTER-MEMORY-4) touches Complaints, Purchase Requests, Price Tag Requests,
  Sponsorship lists only: no overlap with slice 1; slice 2 builds on it after it merges.

## Behaviour (proposed, pending the owner's answers)

1. Enter or comma turns the typed text into a chip. Pasting text with commas or new lines splits
   into one chip per piece; pasting with only spaces splits on spaces ONLY when every piece has a
   digit (document numbers: "SO371334 SO371402"), otherwise it stays one chip ("Acme Trading").
   Each chip has an x; Backspace in the empty text removes the last chip; the box's x clears all.
2. A chip searches exactly what the box searches today (no new syntax).
3. Combining: see Q1 (recommended: a row shows if it matches ANY chip).
4. Typing without Enter works as today (live, debounced). Text typed beside chips counts as one
   more value under the same rule (Q2).
5. Chips travel like today's search text: repeated `query=` params in the address bar, restored
   on Back and prev/next (Q5 on refresh).
6. Export / selection follow the rows the list shows (server result), as today.
7. Server side only: one SQL query; per column `ILIKE ANY (ARRAY[...])`, so 50 chips do not
   become 50 queries or 50x the predicates. Sorting unchanged.
8. One shared component: `ListSearchInput` gains chips when the page passes `chips`; a page opts
   in once its endpoint reads repeated `query` (an endpoint still on `Optional[str]` would silently
   search only the last chip, so pages are switched on with their backend, never globally).
   Box: chips inside, one line, "+N" when they overflow; focus opens it downward over the rows to
   show every chip (no reflow of the toolbar); 375 px and keyboard.

Edge cases: a value with spaces (customer name) is one chip; duplicates (case-insensitive) are
dropped; more than 200 values -> 422 "at most 200 values" from `multi_text` (box keeps the first
200 and says so); a chip that matches nothing just adds no rows.

Mock v1: `documentation/mockups/SEARCH-CHIPS/index.html`.

## Query cost and the index migration (crew ruling (a), 12 Nov)

Measured on a prod-size synthetic copy (211,570 SOs, 887,180 lines, 15,621 products, 6,905
customers, 117 agents): the per-column `ILIKE ANY` clause is a seq scan on sales_orders, 585 ms
at 1 value, 1.1 s at 3, 13 s at 50 (the page runs it twice). With GIN trigram indexes on
sales_orders (so_number, debtor_name, project_label, po_ref, po_ref_key) and the three lookups
rewritten as `= ANY(ARRAY(SELECT ...))` (customer, agent, line product), Postgres uses one
BitmapOr: 32 ms at 50 values. One migration, CONCURRENTLY, IF NOT EXISTS, own `ix_search_trgm_`
names; products / customers indexes only where no trgm index already covers the column
(migration 169 may or may not be present in prod). All indexes in one revertable commit.

## Roll-out (slice 2, new branch + PR after the slice-1 hand test)

`<ListSearchInput` usages by module (non-test files): project-sales 30, system-management 22,
master-data-management 22, scm 20, procurement-management 15, user-management 13,
sla-management 7, dealer-kit 7, resource-management 6, order-management 6, sales 5,
marketing-management 5, inventory-management 5, integration-management 3,
complaint-management 3, others 8. Backend work per list = read `query` with `multi_text` and OR
the service's existing search clause over the values (97 route files declare a free-text `query`).
Proposed order: document lists people search by number first (Delivery Orders, Purchase Orders,
Consignments, Project Sales Orders / Quotations, Order Inquiries, Proforma Invoices), then
customer / product / contact masters, then admin lists. Pickers and dialogs keep the plain box.

## Tests (to be written by the tester after the answers)

To be filled from the UAC.
