# PLAN: OI detail filters survive prev/next; snapshot OI/SO views show project + customer

Status: in progress (small fix track: FE-only expected, no migration, no RBAC change)

Lane: OI-UX-FILTER-SNAPSHOT. Owner ask 3 Nov 19:15.

## Journey

1. CS opens an Order Inquiry, filters its lines (State = reserve, a search, a sort), then
   presses next/previous OI. Today the filter is lost. After: the same lines filter, search and
   sort apply on the next OI, kept in the URL like the other grids.
2. Planner opens a Stock Debt snapshot drill. Each order inquiry group and each sales order line
   names only the document number. After: they also name the customer and the project, in the
   format used elsewhere: `CUSTOMER (PROJECT) / project code`.

UAC: `oi-ux-filter-snapshot-acceptance-criteria.md`.
