# PLAN: scope product bulk delete and pending-action reads to the company

Status: in progress (small fix track: under 300 lines, no migration, no permission slug change)

Lane: SEC-PRODUCT-SCOPE. Follows #2019 (product write routes gated by
`master_data.products.*`, which already covers `DELETE /master-data/products/bulk`
(`.bulk_delete`) and `DELETE /master-data/products/{id}` (`.delete`)).

## Changes

1. `ProductService.bulk_delete_products` deletes row by row through the scoped ORM read,
   with the same refusal guards `delete_product` runs, instead of a bulk
   `query(...).delete()` the company scope filter does not cover (it filters SELECTs only).
   An id outside the caller's scope is not found and not counted, the same rule
   `bulk_update_products` follows. All-or-nothing: one guarded row refuses the batch.
2. `GET /pending-actions/current` answers only for a row whose stored requester scope
   overlaps the reader's own company scope. A reader with every company sees every row.

## Acceptance

- A1 bulk delete naming another company's product leaves it in place, deleted_count 0.
- A2 bulk delete of own-company products still deletes them.
- A3 bulk delete refuses (409) when one row is held by a companion rule, and deletes nothing.
- A4 `/current` for a record whose pending / last action was parked by another company's
  user returns `pending: null, last_outcome: null`.
- A5 `/current` for a same-company action still returns it.
