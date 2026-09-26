# PLAN - Products list: "Discontinued at" column, sort and date-range filter

Status: in review, PR #1292; all ACs green, browser pass at 1280 + 375 (Track: full - carries a data-only list-query catalog seed migration, so not small-fix). Plan created 2026-09-26.

**UAC:** `products-discontinued-at-26sep-acceptance-criteria.md` (the contract). **Issue:** #1287.
**Branch:** `feat/products-discontinued-at-filter`.

## Ruling

> "The thing in our product is we need to have a filter to filter the date range of discontinued at because our system do store the discontinued at and discontinued batch. I think the discontinued batch is not so useful, but the discontinued at is very important. So we need to have the column of discontinued at beside the discontinued column. We should be able to sort by that, to filter by that in a date range. So we need to use a very nice date range picker, which can be typed and also select a from and to in one single calendar. So try to find some existing calendar component in our system."
>
> - Owner, 26 Sep 2026 ~14:00Z, issue #1287

Journey: see the UAC. Every AC below traces to one of its steps.

## Measured facts

- "Discontinued at" is `products.discontinued_notified_at` (naive UTC DateTime,
  `sorento_crm_backend/app/models/product.py` ~263). Stamped with `datetime.utcnow()` by the
  15-minute scheduled task `product_discontinued_check`
  (`app/services/product_discontinued_notify_service.py`); cleared to NULL when
  `is_discontinued` flips True->False. `discontinued_notify_batch_id` is untouched (owner: not
  useful).
- The Discontinued pill derives from `products.is_discontinued` (`ProductsList.tsx` column id
  `is_discontinued`).
- Sort: `ProductService._build_list_query` `sort_map` (`app/services/product_service.py` ~452)
  already emits NULLS LAST both directions with a `Product.id` tiebreak.
- Export fields come from the DB-seeded `list_query_fields` catalog (migrations 101/128/503),
  not grid columns; no row exists for `discontinued_notified_at`.
- `components/ui/date-range-picker.tsx` (`DateRangePicker`) is already the design-system range
  control: typed `DD/MM/YYYY - DD/MM/YYYY` (or one date = one day) parsed on blur/Enter, plus
  ONE react-day-picker calendar (`numberOfMonths=1`, `mode="range"`), Clear/Done. In use by
  StockDebtClient, SalesOrdersGrid, ReportFilterBar, RegisterProjectDialog.
- `lib/listing-column-preferences/mergeColumnOrder.ts` already anchors a new column to its
  neighbour for users with a saved order.

## Design

### Backend seam (no schema migration)

- `app/schemas/product.py` `ProductResponse`: add `discontinued_at: Optional[datetime]` with
  `validation_alias="discontinued_notified_at"` (same pattern as `is_variant`). List, detail and
  list-query rows all carry it (AC-COL-3). Assert the field in a test (response_model drops
  undeclared fields).
- `sort_map` gains `"discontinued_at": Product.discontinued_notified_at` (AC-SORT-1).
- Filter: optional `discontinued_from` / `discontinued_to` (`date`, YYYY-MM-DD, so malformed =
  422 for free, AC-FLT-3) on GET `/api/v1/master-data/products`, and the same two fields on
  `ListSearchRequest` and `ListExportRequest` (`app/schemas/list_query.py`), threaded through
  `list_query_search_service._search_products` and `list_query_export_service._export_products`
  into `_build_list_query`. One helper converts a Malaysia day to naive UTC:
  from -> `>= from 00:00 MYT`, to -> `< (to + 1 day) 00:00 MYT`; either bound adds
  `IS NOT NULL` (AC-FLT-1/2/4, AC-EXP-2). One helper, three callers; no registry.

### Migration (data only)

- `alembic/versions/<file>_prod_discontinued_at_flt.py`, revision `prod_discontinued_at_flt`,
  `down_revision = "sales_0002_team_leader"` (re-parented onto main by `alembic-reparent.sh`), same `seed()/upgrade()/downgrade()` shape as
  `503_product_exclude_planning_flt.py`. Inserts `field_key "discontinued_at"`, label
  "Discontinued at", `data_type date`, `compile_key product.discontinued_notified_at`,
  `export_column_name "Discontinued at"`. Downgrade deletes that row.
- `scripts/bootstrap_env.py` `seed_products_list_query_fields` calls the new `seed()` too.
- Export value is the Malaysia calendar date (YYYY-MM-DD), not the raw UTC timestamp (AC-EXP-1).
- Run `./scripts/alembic-reparent.sh` at the pre-PR gate; single head.

### Frontend seam

- `app/(protected)/master-data-management/products/components/ProductsList.tsx`: column id
  `discontinued_at` right after `is_discontinued`; `formatDateInMalaysia` DD/MM/YYYY, blank when
  null; explicit `size`; sortable server-side (`manualSorting`); hideable (AC-COL-1/2, AC-SORT-2).
- Filters popover: "Discontinued between" `DateRangePicker`, counted in the active-filter count,
  one chip through the toolbar's existing `activeSummary` ("Discontinued: 1 Sep 26 - 26 Sep 26",
  "Discontinued: from X", "Discontinued: to Y"), chip x and Clear Filters clear both ends;
  changing it resets to page 1 (AC-FLT-5/6, AC-TYPE-1).
- Plumbing: `lib/listQuery.ts` `productsListQueryKey`, `fetchProductsPage` (GET and
  advanced-filter POST), `productsListParamsFromUrl`, `useListStateFromUrl` restore, and the
  Export payload (AC-EXP-3). Layering unchanged: UI -> hook -> service -> `lib/api-client`.
- Layout: DataGrid + CardTable already scroll sideways in their own scroller; check 375 px and
  1280 px (AC-MOB-1).

### Component reuse decision

Reuse `DateRangePicker` unchanged. It already meets both owner asks (typeable, one calendar for
from and to). No new dependency, no component edit.

### Impact checklist

RBAC / module guard: none (existing products view permission). list_query registry code: none,
catalog row only. Embeddings: none (dates not embedded). Worker / RQ: none. Preferences: none.

## Test list (Phase 2, written red first)

- `sorento_crm_backend/tests/test_product_discontinued_at_list.py` (Postgres fixture, seeds its
  own products): AC-COL-3, AC-SORT-1, AC-FLT-1 (incl. 16:30 / 15:59 / next-day 16:00 UTC
  boundaries), AC-FLT-2, AC-FLT-3, AC-FLT-4, AC-EXP-1 (catalog row + MYT value), AC-EXP-2.
- `sorento_crm_frontend/app/(protected)/master-data-management/products/components/ProductsList.discontinuedAt.test.tsx`
  (vitest): AC-COL-1, AC-COL-2, AC-SORT-2, AC-FLT-5, AC-FLT-6, AC-TYPE-1, AC-EXP-3.
- AC-MOB-1: agent-browser evidence run at 375 px and 1280 px, navigated from `/` via sidebar.

## Data caveat

The value is when the scheduler noticed, not when a user flipped the flag: blank for up to 15
minutes after discontinuing, and for products already discontinued when the notify feature
shipped it is that first tick's time. No backfill is possible; no earlier date is stored.

## Not in this lane

- Existing Discontinued column is marked sortable but `is_discontinued` is not in `sort_map`,
  so clicking it silently sorts by `created_at`. Adjacent defect; separate issue.
- `discontinued_notify_batch_id` in the UI (owner: not useful).
- Any backfill or change to the stamping task.
