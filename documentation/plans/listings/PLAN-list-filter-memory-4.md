# PLAN - LIST-FILTER-MEMORY-4: four more lists remember sort and filters

**Status:** Build (small fix track: under ~300 lines, no migration, no auth/RBAC change, no new ingest)
**Owner ask (12 Nov 2026):** the list-filter memory Sales Orders and Stock Inquiry have must also apply to
Complaints, Purchase Requests, Price Tag Requests and Sponsorship Forms.
**Mechanism (mirrored, not new):** `useListingViewPreferences`
(`sorento_crm_frontend/lib/listing-column-preferences/useListingViewPreferences.ts`), design and UAC in
`documentation/plans/_archive/listings/PLAN-listing-view-memory.md`.

## What the two existing lists do (they agree, so there is one thing to mirror)

| Behaviour | Stock Inquiries | Sales Orders |
|---|---|---|
| Hook | `useListingViewPreferences` (`StockInquiriesList.tsx:101`) | same (`SalesOrdersGrid.tsx:286`) |
| Listing key | `pathname` (the key DataGrid uses for columns, one row per user per list) | `listingKey ?? pathname` |
| Remembered | sort + filters blob, `filtersVersion` | same |
| Not remembered | page number, search text (URL only, `useListStateFromUrl`) | same |
| Data query | held until the stored view is applied (`enabled: !isViewPrefsLoading`) | same |
| Clear | `setFilters(null)` (explicit null, stored as no filter) | same |
| Filter chip | `activeSummary { label, onClear }` | same |
| Per user | yes: `user_list_column_configs (user_id, listing_key)` server-side | same |

## Changes

- `ComplaintsList.tsx`: sort + 4 filters (assigned to, status, root cause, resolution) into the blob, v1.
- `PurchaseRequestsList.tsx` (serves both `/procurement-management/purchase-requests` and
  `/procurement-management/sponsorship-forms`; the pathname key keeps them apart): sort + status + assigned to
  (+ type on the combined list), v1.
- `PriceTagRequestsList.tsx`: sort + status, v1; its hand-rolled fetch waits for the stored view.
- Each list: URL keeps page + search only (as SO/SI); filter changes reset to page 1 inside the apply helper;
  `activeSummary` chip with Clear.

## Tests (red first)

One `*.viewMemory.test.tsx` per component (PR and Sponsorship both covered in the PR file), rendering the real hook
with only the preferences transport and data hook stubbed: stored sort+filters apply before the one fetch (survives
leaving and coming back / reload, since both re-read the stored row), a change is written for that listing key,
Clear writes an explicit null and refetches unfiltered. Per-user isolation is server-side and already pinned by
`sorento_crm_backend/tests/test_list_view_memory.py`.

## Standing rules that apply

Filters & search: "Filters, sort and search survive prev/next ... and the way back to the list"; "Every dropdown
filter is multi-select". Lists: one toolbar row; server-side sort.
