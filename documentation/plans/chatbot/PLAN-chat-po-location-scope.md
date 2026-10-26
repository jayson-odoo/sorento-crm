# PLAN: on-order (PO / SPO) lines shown to a contact respect its location scope (CHAT-PO-LOCATION-SCOPE)

Status: in progress (small fix track, size S: no migration, no RBAC change, no new ingest surface)

UAC: `chat-po-location-scope-acceptance-criteria.md` (beside this file).

## Problem (owner report, 26 Oct 2026, prod)

A contact allowed only some locations (BRW, MWH) asked for stock of a product with 0 stock. The
stock lines were scoped (BRW, MWH only), but the "Stock is 0 at every location and no incoming
for X, but PO is placed:" list under them printed every open PO line of the product, two of them
with no `Location:` line. Those two are the lines on BRW-BB / BRW-NTC: locations the contact may
not see.

## Cause

- The list is the cross-domain ladder's purchase-order rung
  (`app/services/chatbot/lanes/business/answer.py` `_CROSSDOMAIN_RUNG_TOOL`, header text
  "but PO is placed" at answer.py:1566-1572). It calls `crm_procurement_po_placed_list`, i.e.
  `GET /procurement/purchase-orders/placed`, with the contact's `contact_id` / `space_id`.
- That route (`app/api/v1/procurement/purchase_orders.py:176-187`, added by #1431
  STOCK-TOTAL-OS-SCOPE as a tester finding) KEEPS every row and only nulls `location` when the
  location is outside `stock_visibility.visible_location_codes`. So out-of-scope lines are shown,
  just unnamed: exactly the rows printed without a location.
- The stock lines are scoped by `stock_visibility.warehouse_criterion(policy, <warehouse id>)`
  (stock_visibility.py:364), applied in `inventory_service` (lines 708-745, fail closed on an
  unresolvable contact) over EXACT warehouse ids.

## Sub-location rule (from code, not invented)

`StockVisibilityPolicy.warehouse_ids` / `excluded_warehouse_ids` (`app/models/access.py:915-921`)
name warehouse ROWS, and `warehouse_criterion` tests `column.in_(ids)` / `notin_(ids)` with no
pool or prefix expansion. BRW-BB and BRW-NTC are their own `warehouses` rows (segment `project`,
`pool_warehouse_id` -> BRW, `app/models/inventory.py:46-60`). So a contact scoped to BRW does NOT
see BRW-BB stock lines, and must not see BRW-BB PO lines either. No ask needed.

## Fix (one shared scope function)

1. `stock_visibility.py`: replace `visible_location_codes` (its only caller is the placed route)
   with `scope_warehouse_ids(db, policy)`: None when the policy names neither list, else the ids
   of the ACTIVE warehouses `warehouse_criterion(policy, Warehouse.id)` allows - the same set the
   stock lines and their `stock_visibility.warehouse_codes` echo are built from.
2. `GET /procurement/purchase-orders/placed` with `contact_id`:
   - `resolve_policy` None (unresolvable contact): no rows, the stock list's own fail-closed answer.
   - scope ids not None: they narrow `warehouse_ids` (intersect with any the caller named) BEFORE
     the query, through the existing `warehouse_ids` filter (PO line `warehouse_id IN`, SPO by
     warehouse id or location code, `spo_warehouse_predicate`). Rows AND `summary` read the same
     narrowed set. Empty set: no rows, zero summary.
   - `availability` mode: rows scoped the same way, `location` still withheld (it names no
     location at all, as today).
3. A PO line with NO warehouse is outside every named scope (SQL `IN` fails on NULL). Same ruling
   the owner made for open SO with no warehouse in #1431 (option b: no Unassigned line).
   Dev data (`sorento_cagent_stack`, read-only): 944 of 4,705 open PO lines have no warehouse,
   mostly 2019-2022; every pending SPO allocation has one.
4. Contacts whose policy names no location list (staff, the inert default) and calls without
   `contact_id` (n8n, staff UI): unchanged.

## Other surfaces checked

See the lane report; each incoming / PO / SPO surface reachable with a `contact_id` is listed
with its scope rule.

## Tests (red first)

`tests/test_po_placed_contact_scope.py` (throwaway DB): a contact scoped to BRW + MWH, a product
with 0 stock and open PO lines at BRW, BRW-BB, BRW-NTC (+ one with no warehouse, + one SPO at
BRW-BB): the placed route returns only the BRW line (with its location); summary counts it alone;
exclusion policy; availability mode (scoped rows, no location); unresolvable contact (no rows);
no contact (every row). Plus the rendered rung text for the owner's case.

## Eval gate

No prompt or parser change: the rung's wording is untouched, only which rows the CRM returns.
`documentation/agents/chatbot-verification.md` decides whether a console check is owed.
