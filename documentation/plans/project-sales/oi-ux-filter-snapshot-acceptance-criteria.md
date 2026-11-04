# UAC: OI-UX-FILTER-SNAPSHOT

- AC-1: On an OI detail page, the lines grid's search, filters and sort are held in the URL.
- AC-2: Pressing next/previous OI keeps those query params, so the next OI's lines open with the
  same search, filters and sort.
- AC-3: Reloading an OI detail page with those params restores the same lines view.
- AC-4: The Stock Debt snapshot drill names each OI group by its number only (owner hand test,
  4 Nov: the `CUSTOMER / project` line under the OI heading is struck out, since the group's
  table already has Customer and Project columns). The format below still applies to the
  columns and to compact places with no such table. Format (crew answer (a), 3 Nov): grids get the SO list's own **Customer** and
  **Project** columns; compact places print one line `CUSTOMER / project`, where CUSTOMER is the
  debtor name (AutoCount's, which usually already ends `(PROJECT)`), so it reads as the owner's
  `CUSTOMER (PROJECT) / project code`.
- AC-5: Each sales order line in the snapshot drill shows the same customer / project label.
- AC-6: A missing customer or project prints a dash in its place, never an id
  (`ACME SDN BHD / -`, `- / TAMAN JAYA`); nothing extra when the order names neither.
- AC-7 (owner widening, 3 Nov 19:35): every place a sales order is shown names its customer and
  project the same way (inventory: `oi-ux-filter-snapshot-so-inventory.md`); a new column on a
  server-paged grid sorts on the server.
- AC-8 (security review): a billing document's line names its sales order (id, customer,
  project) only to a viewer who may open sales orders, the same rule as its header list.
