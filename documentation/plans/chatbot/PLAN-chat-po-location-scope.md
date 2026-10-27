# PLAN: on-order (PO / SPO) lines shown to a contact respect its location scope (CHAT-PO-LOCATION-SCOPE)

Status: in review, PR #1880 (small fix track, size S: no migration, no RBAC change, no new ingest surface)

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
4. Contacts whose policy names no location list (the inert default included) and calls without
   `contact_id` (staff screens, a direct MCP / n8n call naming no contact): unchanged. The
   chatbot sends `contact_id` for staff contacts too, so a staff contact whose policy names a
   location list gets on-order lines scoped to it, the same as its stock lines.

## Other surfaces checked (known gap, follow-up lane)

Crew ruling (a), 26 Oct: this lane ships the PO / SPO on-order fix only. The incoming routes
(`app/api/v1/incoming_stock.py:426-539`, `:230-332`, `:542-565`, whose `Warehouse Allocations`
the MCP presenter prints, `sorento_crm_mcp/presenters.py:924-926`, `:970-972`) and the SPO
last-in route (`app/api/v1/procurement/spo_allocations.py:34-120`, no `contact_id` at all) do not
read the contact's location scope; a follow-up M lane takes them with a behaviour card. The stock
answer's Total O/S (#1431) and the dealer-mode ETA have no gap.

## Tests (red first)

`tests/test_po_placed_location_visibility.py` (route level, throwaway DB; its old tests pinned
"row stays, location blanked" and are rewritten): the owner's case (BRW + MWH contact, 0 stock,
PO lines at BRW, BRW-BB, BRW-NTC: only the BRW lines, summary 40 / 2); include list, exclusion,
merged access-type policy, empty include list, a named warehouse never widens; PO line with no
warehouse; SPO by location code (hidden dropped, visible kept); availability (scoped, no
location); unresolvable contact (no rows); every-location policy and no contact (unchanged).
The rung's rendering is unchanged and already covered by `tests/chatbot/test_crossdomain_ladder.py`.

## Eval gate

No prompt or parser change: the rung's wording is untouched, only which rows the CRM returns.
`documentation/agents/chatbot-verification.md` decides whether a console check is owed.
