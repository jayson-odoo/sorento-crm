# PLAN: scope product bulk delete and pending-action reads to the company

Status: in review (small fix track: under 300 lines, no migration, no permission slug change)

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
- A6 a row with no stored scope falls back to the requester's explicit company grants.
- A7 parking an action on a record another company is counting down answers 409 without
  echoing that company's action id or timing.

## Known limits (accepted)

- An action parked by an all-companies principal is hidden from single-company readers,
  including the record's own company: a second park there gets the generic 409 with no
  countdown on screen.
- The read check compares the requester's scope with the reader's, not the record's
  company. Only `contact_customer_link.unlink` parks under a widened scope today.
- A park-time record visibility check for every action key is a follow-up lane.
- TODO(#2020): the quotation-in-use delete guard joins `bulk_delete_products` when that
  lane merges.

## Follow-up

Other bulk writes on company-scoped models were surveyed; the ones that need the same
treatment are queued as their own lanes.
