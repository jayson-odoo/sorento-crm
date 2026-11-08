# PLAN - Products list: list price changed-between filter, changed-at column, change-history lightbox

Status: Plan (behaviour card posted as crew-ask; Track: small-fix candidate, decided once the diff is sized). Plan created 2026-11-08.

crew-lane: LIST-PRICE-CHANGE-UI. Base: main cffaece6 (#2228 list-price change notifications).

## Ruling

> "for the list price, follow like discontinued: we have this kind of filter and column, and it is good if we can show
> the change of list price here with some icon that opens the lightbox popup that shows the change; reuse as much
> component as possible; do it according to our system design principles."
>
> - Owner, 8 Nov 2026 ~21:00

## Measured facts

- Discontinued precedent: PLAN `_archive`/`PLAN-products-discontinued-at-26sep.md`. Column `discontinued_at`
  (alias of `products.discontinued_notified_at`), `sort_map` entry, `discontinued_from/_to` date filter
  (Malaysia day -> naive UTC) on GET products + list-query search/export, `DateRangePicker` in the Filters popover.
- #2228 watermark: `products.list_price_notified` / `list_price_notified_at` / `list_price_notify_batch_id`
  (`sorento_crm_backend/app/models/product.py:381-383`), stamped by `product_list_price_check` every 15 min
  (`app/services/product_watched_field_notify_service.py:544`). `list_price_notified_at` is NULL for every product
  whose price has not changed since #2228 shipped (backfill set only `list_price_notified`).
- Audit trail: every ORM product UPDATE writes `audit_logs` with ONLY the changed keys in `old_values`/`new_values`
  (`app/services/audit_service.py:157`). The AutoCount ingest writes through the ORM (`master_ingest_service.py:1638`),
  so its price changes are audited (`actor_type='integration'`). Source label rule already exists:
  `_list_price_sources` (`product_watched_field_notify_service.py:440`).
- A product's audit history is already readable by `master_data.products.view` holders
  (`app/api/v1/audit/audit_logs.py:31`).
- Lightbox: `components/ui/dialog.tsx` (every Dialog is a modal lightbox, `dialog.lightbox.test.tsx`).

## Design (draft, pending the behaviour card answers)

- Column + sort + filter: `list_price_changed_at` = `products.list_price_notified_at`, exactly the discontinued seam.
- Icon in the List Price cell when `list_price_changed_at` is set; opens a `Dialog` listing the product's list-price
  audit rows newest first: date (dd/mm/yyyy), old -> new, % change, by (AutoCount sync / staff name / blank).
- One read endpoint `GET /api/v1/master-data/products/{id}/list-price-history`, products view permission, product
  loaded through the company-scoped ORM.
