# PLAN: Stock position totals follow the visible columns

Status: Merge-ready (2 Nov): reviewer READY, browser pass 1280/375 green. Track: small fix (no migration, no RBAC change, no new ingest surface; the diff runs ~350 lines with tests and docs, a little over the ~300 guide). Q1 answered (a): both totals follow visibility.

Lane: STOCK-POS-DYNAMIC-TOTAL. Owner request 2 Nov ~23:20, Inventory > Stock position: the total of
incoming and on-hand "needs to be dynamic according to the columns shown in the table ... if I hide
BMW-RSV, the Total Quantity column must be calculated accordingly".

This reverses Q5's last sentence in `PLAN-stock-position-report-27oct.md` ("Hiding a column does not
take that warehouse out of Total stock"). The owner's word is "Total Quantity"; the screen's column is
**Total stock** (warehouse columns + Incoming BRW), the one whose parts are "incoming and all the stock on
hand". UAC: `stock-pos-dynamic-total-acceptance-criteria.md`.

## Where the totals are computed today

- Server, per row: `sorento_crm_backend/app/services/stock_position_service.py:191` (Total stock = every
  warehouse column + Incoming BRW) and `:205` (Total incoming = Incoming BRW + Incoming (Project)).
- Server sort: `stock_position_service.py:227` `_sort_key` reads the stored `total_stock` / `total_incoming`.
- Export: `stock_position_service.py:294` `workbook` hides warehouse columns (`wh`) but writes the full totals
  (docstring says so on purpose).
- Grid: `sorento_crm_frontend/app/(protected)/inventory-management/stock-position/components/StockPositionGrid.tsx:142`
  prints the server's `total_stock` / `total_incoming`; column visibility is the DataGrid's own state, saved per
  user by `useListingColumnPreferences` (this page mounts no saved-views menu); the grid never sends it to the API.

## The rule

| Total | Built from | Hidden part |
| --- | --- | --- |
| Total stock | each warehouse (location) column + Incoming BRW | drops out of the total |
| Total incoming | Incoming BRW + Incoming (Project) | drops out of the total |

- 0 visible warehouse columns: Total stock = Incoming BRW (if shown), else 0.
- Every part hidden: the total is 0 (the column itself can still be shown).
- The other columns (packing list, outstanding, sales) are no part of any total and are unaffected.
- The header tooltip names what the total adds up ("Sum of BRW, DC1, Incoming BRW"; "Sum of none" when every part is hidden); the chooser keeps the plain name.

## Contract

`GET /api/v1/inventory/stock-position` and `/export` take `hide` (repeatable): the column ids the user hides
(`wh:<code>`, `incoming_pool`, `incoming_project`; any other id is ignored). Absent = nothing hidden. The server
recomputes both totals per row from the shown parts BEFORE sorting, so sort by a total, paging and the export
all read the same visible set. The export's warehouse and incoming columns follow `hide` too (the old `wh` list is retired;
the grid is its only caller). A hidden-list rather than a shown-list so a warehouse that starts holding stock
appears, and counts, by default.

The grid controls `columnVisibility` in React state (the saved column layout writes through it), sends
the hidden part-columns in the query key, so a toggle refetches page 1 at once.

## Questions (recommendation in each; building on the recommendation meanwhile)

1. Total incoming follows the same rule? Rec: yes, it is the other "sum of columns" and the same rule reads
   cleanly; say no and it stays fixed.
2. Filters are single-select today (Supplier, Brand, Warehouse), not multi-select; the API already takes lists.
   Rec: a separate small lane, not this one, so this diff stays the total.
