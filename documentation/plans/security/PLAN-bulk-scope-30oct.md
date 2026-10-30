# PLAN: scope bulk deletes to the company

Status: in progress (small fix track: under 300 lines, no migration, no permission slug change)

Lane: SEC-BULK-SCOPE. Follows #2024 (product bulk delete).

## Changes

1. `OrderService.bulk_delete_orders`, `MarketingService.bulk_delete_promotions` and
   `InventoryService.bulk_delete_stock` read their rows through the company-scoped ORM query,
   run the same refusal guards their single delete runs, and delete row by row, instead of a
   bulk `query(...).delete()` the scope filter does not cover (it filters SELECTs only).
   An id outside the caller's scope is not found and not counted.
2. Parking a pending action (`POST /pending-actions`) checks the caller can see the record.

## Acceptance

Written with the tests; see the test file named in the PR.
