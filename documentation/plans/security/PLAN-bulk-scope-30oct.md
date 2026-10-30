# PLAN: scope bulk deletes to the company

Status: in review (small fix track: under 300 lines, no migration, no new permission slug)

Lane: SEC-BULK-SCOPE. Follows #2024 (product bulk delete).

## Changes

1. `OrderService.bulk_delete_orders`, `PromotionService.bulk_delete_promotions` and
   `StockService.bulk_delete_stock` read their rows through the company-scoped ORM query and
   delete row by row, the way each single delete does, instead of a bulk `query(...).delete()`
   the scope filter does not cover (it filters SELECTs only). An id outside the caller's scope
   is not found and not counted. None of the three single deletes has a refusal guard to reuse.
2. The promotion bulk and single delete routes and the order single delete route ask for the
   existing `.delete` slug (`marketing.promotions.delete`, `order_management.orders.delete`),
   the one the screens already gate the button on. Order and stock bulk deletes already did.
3. Parking a pending action (`POST /pending-actions`) reads the record under the caller's company
   scope first, for every record action on a company-owned table (`_PARK_SCOPED_MODELS`). A key
   that is not read that way is named, with its reason, in `_PARK_SCOPE_EXEMPT`; a test fails
   when a new record action is in neither.

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

Tests: `sorento_crm_backend/tests/test_bulk_delete_company_scope.py`.

## Known limits (accepted)

- Other bulk writes on company-scoped models were surveyed and listed in the lane report; they
  are queued as their own lanes.
