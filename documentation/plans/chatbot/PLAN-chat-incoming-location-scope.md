# PLAN: incoming supply shown to a contact respects its location scope (CHAT-INCOMING-LOCATION-SCOPE)

Status: Build (size M, chatbot, backend-only; behaviour card posted on PR #1882, built on the
recommended answers until the owner says otherwise). Stacked on CHAT-PO-LOCATION-SCOPE (#1880)
to reuse its `stock_visibility.scope_warehouse_ids`.

UAC: `chat-incoming-location-scope-acceptance-criteria.md` (beside this file).

## Problem

Owner rule (26 Oct 2026): supply shown to a contact respects the contact's allowed locations, the
same scope as its stock lines. #1880 fixed the PO / SPO on-order rung only. Still open:

- `GET /incoming-stock/list`, `/by-product`, `/shipments`, `/shipments/{id}/products`
  (`app/api/v1/incoming_stock.py`) never read the stock-visibility policy.
  `IncomingStockService._warehouse_allocations_for` (`incoming_stock_service.py:268`) returns
  every warehouse's allocation; the MCP presenter prints them as `Warehouse Allocations`
  (`sorento_crm_mcp/presenters.py:924`, `:970`), kept always (chatbot `fetch.py` IDENTITY_KEYS).
- `GET /procurement/spo-allocations/last-receipt` (`spo_allocations.py:34`) declares no
  `contact_id` (the MCP catalog sends one; the company-scope resolver reads it), so location
  scope never applies and every row names `warehouse`.
- The parser's LOCATION lookup list (`chatbot/head/lookup_lists.py:506`) offers every active
  warehouse of the session's companies.

## Answers assumed (behaviour card Q1-Q5, recommendations)

- Q1 (a) a scoped contact's line `remaining_incoming_quantity` = min(line remainder, sum of the
  in-scope outstanding allocations).
- Q2 (b) `unallocated_quantity` is not shown to a scoped contact (no warehouse = no named
  location; #1431 option b, #1880 AC-4).
- Q3 (a) a line with no in-scope quantity is not returned; a shipment / product left with no line
  is not returned.
- Q4 (a) last-in rows outside scope are dropped, narrowing `warehouse_ids` before the pick.
- Q5 (a) the LOCATION lookup rows are the scope's warehouses only.

## Design (one scope function)

1. Scope = `scope_warehouse_ids(db, resolve_policy(db, contact_id, space_id))`, computed once per
   request. `None` = no filter (no contact, or a policy naming no location list). A list = allowed
   warehouse ids. Unresolvable contact = `[]` (fail closed).
2. `IncomingStockService(db, regions=..., warehouse_scope=...)`. When `warehouse_scope` is not
   None:
   - `_warehouse_allocations_for` also filters `SPOAllocation.warehouse_id IN scope`.
   - Every line query gets an EXISTS filter: an in-scope, visible (`spo_supply.visible_line_clauses`),
     `allocated_quantity > 0` SPO allocation of the same shipment + product with outstanding
     quantity > 0 (the same outstanding expression `_warehouse_allocations_for(outstanding_only)`
     uses). SQL, so pagination and totals count only visible lines/shipments.
   - Line quantity = min(remainder, in-scope outstanding sum); `unallocated_quantity` = None.
   - `/shipments` `total_remaining_incoming_quantity` / `distinct_products_incoming` recomputed from
     the scoped lines.
3. `_Contact` (`incoming_stock.py`) resolves the scope with the rest of the contact's rules and
   hands it to the service on every route.
4. Last-receipt: `contact_id` / `space_id` declared; scope narrows `warehouse_ids` exactly as the
   placed route does (#1880); empty scope = no rows; `availability` withholds `warehouse`.
5. Lookup list: `load_rows(..., warehouse_scope=...)`; `engine.py` passes the resolved contact's
   scope (no contact id in play = unchanged; given but unresolvable = no location rows).

## Tests (red first)

`tests/test_incoming_location_scope.py` (blank schema, every row seeded): E1-E5 of the card on
`/list`, `/by-product`, `/shipments`, `/shipments/{id}/products`; dealer (availability) view;
unresolvable contact; no contact and an every-location policy unchanged (allocations, unallocated);
pagination total. `tests/test_spo_last_receipt_location_scope.py`: drop before the pick, availability
withholds warehouse, unresolvable no rows, no contact unchanged. Lookup list: `_location_rows` / 
`load_rows` with a scope.

## Eval gate

No prompt or parser wording change; the LOCATION lookup block is advisory and only narrows.
`documentation/agents/chatbot-verification.md` decides the console check.
