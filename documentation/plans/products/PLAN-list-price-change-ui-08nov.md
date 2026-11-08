# PLAN - Products list: list price changed-between filter, changed-at column, change-history lightbox

Status: merge-ready on PR #2260, awaiting owner hand test (Track: full - carries a data migration). Plan created 2026-11-08.

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

## Owner rulings (8 Nov ~21:20, answers to the behaviour card on #2260)

- Q1 (a): backfill `list_price_notified_at` from the latest audited list-price change, only where NULL and not pending.
- Q2 (a): the history icon shows only when "List price changed at" is set.
- Q3: the lightbox is the STANDARD DataGrid list view with server-side pagination and sortable columns, dd/mm/yyyy.
- Q4 (a): export column "List price changed at" (catalog seed row, like discontinued).
- Q5: include the create-time price as an "Initial price" row (crew confirming the reading; one switch,
  `INCLUDE_INITIAL_PRICE` in `app/services/product_list_price_history_service.py`).

## Design (as built)

- Column + sort + filter: `ProductResponse.list_price_changed_at` = `products.list_price_notified_at`; `sort_map`
  key `list_price_changed_at`; `list_price_changed_from/_to` on GET products, `ListSearchRequest` and
  `ListExportRequest`, through one `malaysia_day_range_filters` helper (`product_service.py`) that the
  discontinued range now uses too.
- History: `GET /api/v1/master-data/products/{id}/list-price-history?page&limit&sort&dir`, product loaded through the
  company-scoped ORM first (404 otherwise, the `/purchase-history` gate). One SQL over `audit_logs` (UPDATE rows
  carrying `list_price`, numeric no-ops skipped, plus the CREATE row as `kind: initial`), "by" from the #2228 rule
  (`SYNC_SOURCE_LABEL` for an integration, the staff name for a user, nothing otherwise), every column sorted on the
  server, nulls last, ties newest first. Shape `{data, pagination}`.
- Migration `lpcui_0001_list_price_changed`: `backfill_changed_at()` + `seed()` (export-only catalog row, Malaysia
  date on export); `scripts/bootstrap_env.py` replays `seed()`.
- FE: "List price changed at" column right after List Price; "List price changed between" `DateRangePicker` with
  its own chip beside the discontinued one (`activeSummary` array); history icon (lucide `History`, `Button`
  icon mode) in the List Price cell; `ListPriceHistoryDialog` = `Dialog` + `DataGrid`/`DataGridTable`/
  `DataGridPagination` with manual paging and sorting. The dead `getPriceHistory`/`useProductPriceHistory`
  stubs (they called a `/price-history` route that never existed) now carry this endpoint; no parallel service.

## Tests

- `sorento_crm_backend/tests/test_product_list_price_change_ui.py`
- `sorento_crm_frontend/app/(protected)/master-data-management/products/components/ProductsList.listPriceChange.test.tsx`
- `sorento_crm_frontend/app/(protected)/master-data-management/products/components/ListPriceHistoryDialog.test.tsx`
