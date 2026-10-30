# PLAN: scope bulk deletes to the company

Status: in review. Full track, not small fix: the diff adds permission gates to routes and changes
company scoping, so reviewer and security reviewer both ran. No migration, no new permission slug.

Lane: SEC-BULK-SCOPE. Follows #2024 (product bulk delete).

## Changes

1. `OrderService.bulk_delete_orders`, `PromotionService.bulk_delete_promotions` and
   `StockService.bulk_delete_stock` read their rows through the company-scoped ORM query and
   delete row by row, the way each single delete does, instead of a bulk `query(...).delete()`
   the scope filter does not cover (it filters SELECTs only). An id outside the caller's scope
   is not found and not counted. None of the three single deletes runs a refusal guard, so there
   is none to reuse (stock has no single delete).
   Order line bulk delete (owner ruling in the lane) reads the order through the scoped
   `get_order` (404 outside the company) and its lines row by row. Its route moves above
   `/{order_id}/lines/{line_id}`, which matched "bulk-delete" as a line id, so the bulk route
   never ran before.
2. The promotion bulk and single delete routes and the order single delete route ask for the
   existing `.delete` slug (`marketing.promotions.delete`, `order_management.orders.delete`),
   the one the single-delete screens already gate on; the promotions list's bulk Delete is now
   gated on it too. Order line bulk delete asks for `order_management.orders.delete`. Order and
   stock bulk deletes already did. Single order line delete stays sign-in only, like line
   create and edit (orders have no line edit slug).
3. Parking a pending action (`POST /pending-actions`) reads the record under the caller's company
   scope first, for every record action on a company-owned table (`_PARK_SCOPED_MODELS`). A key
   that is not read that way is named, with its reason, in `_PARK_SCOPE_EXEMPT`; a test fails
   when a new record action is in neither. `price_tag_request_tag.delete` is checked (and its
   handler reads) through the tag's request, the way the direct route does.

## Acceptance

- A1 order, promotion and stock bulk delete naming another company's row leaves it in place,
  deleted_count 0.
- A2 a mixed list deletes only the caller's own rows.
- A3 own-company rows still delete.
- A4 promotion bulk / single delete and order single delete answer 403 without the slug.
- A5 parking `order.delete` / `product.delete` on another company's record answers 404 and parks
  nothing; a malformed id answers 404.
- A6 parking on an own-company record still answers 202.
- A7 every record action key is in exactly one of the two park-time lists.
- A8 order line bulk delete on another company's order answers 404 and deletes nothing; own lines
  still delete; without the slug it answers 403.
- A9 parking a price tag delete on another company's request answers 404; own still 202.

Tests: `sorento_crm_backend/tests/test_bulk_delete_company_scope.py`.

## Known limits (accepted)

- A few exempt keys (an SO line attachment, a shipment line photo) hang off a company-owned parent
  but are not read at park time; their commit runs under the requester's stored scope and finds
  nothing.

- Other bulk writes on company-scoped models were surveyed and listed in the lane report; they
  are queued as their own lanes.
