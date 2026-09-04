# PLAN - Listing view memory (sticky sort + sticky filter)

**Status:** Implemented on `fm/listing-view-memory` (pilot: Stock Inquiries). Rolled out to SCM
Sales Orders on `feat/scm-sales-orders-view-memory`, 3 Sep 2026 (section 8 below) - vitest +
agent-browser evidence run done. Two pre-existing bugs the rollout exposed (null order_date
sort order, a no-op customer filter) were fixed in the same lane as a second commit; see
section 8.
**Classification:** CORE - `public` schema, no new table, no migration
**UAC (the contract):** `documentation/plans/listings/listing-view-memory-acceptance-criteria.md`
**Pilot listing:** Procurement Management -> Stock Inquiries

---

## 1. Goal

A user opens a listing and it is already sorted and filtered the way they left it. Purchasing
lands on Pending Purchasing; project sales lands on Pending Project Sales. Nobody configures
anything.

## 2. Current state (verified in the working tree)

| Fact | Where |
|---|---|
| Column order, visibility and width are already remembered for **every** listing | `components/ui/data-grid.tsx:219` - `effectiveListingKey = listingKey ?? pathname`, so all 121 DataGrid listings get it; only 5 pass an explicit key |
| Storage is one JSONB blob keyed by `(user_id, listing_key)` | `user_list_column_configs`, unique constraint `uq_user_list_column_configs_user_id_listing_key` |
| The payload already carries a `version` field | `UserListColumnConfigPayload` in `app/schemas/list_query.py:147` |
| The hook already exposes the gate we need | `useListingColumnPreferences` returns `isLoading: Boolean(key) && !appliedRef.current` |
| `DataGrid` already forwards it | `isColumnPreferencesLoading` on `DataGridProvider` |
| Sort is **not** stored | Page-level `useState`; Stock Inquiries hardcodes `[{ id: 'created_at', desc: true }]` |
| Filters are **not** stored, and have no shared shape | 37 listings hold their own; 23 a bare `string`, 3 a `string[]`, 6 the generic `ListQueryFilterGroup` |
| `stock_inquiries` is **not** in the generic list-query registry | `ADAPTERS` in `app/services/list_query_registry.py` holds 8 resources; stock inquiries is not one |
| The shared toolbar already has a filter slot with an active-count badge | `components/ui/data-grid-list-toolbar.tsx` - `filters.active` / `filters.activeCount` |

## 3. The two decisions that shape everything

### 3.1 The filter blob is opaque to the shared layer

The shared hook and the backend **never interpret** `filters`. The page hands over JSON and
gets the same JSON back. Stock Inquiries stores `{ "statuses": ["pending_purchasing"] }`;
Orders would store its `ListQueryFilterGroup`; neither knows about the other.

This is what makes the feature cheap: no list-query registry work, no listing migration, and
it works today on all 37 bespoke filter shapes. It is the reason the pilot can ship without
touching `stock_inquiries`' absence from `ADAPTERS`.

**Its cost, and the mitigation.** An opaque blob can outlive the page version that wrote it.
Each page declares a `filtersVersion`; the hook stores it alongside the blob and returns
`null` when the stored version does not match. Stale blob is dropped, shipped default is used
(AC-B4). Without this guard a refactor of a page's filter shape breaks that listing for every
user who had a filter saved.

### 3.2 Two writers, one row

This is the trap in the design. Column preferences are written by `DataGrid` from inside the
grid. Sort and filter are written by the page from above the grid. Both target the same
`(user_id, listing_key)` row.

Today the `PUT` handler does `setattr(row, "config", data)` - a **whole-blob replace**
(`app/api/v1/list_query.py:284`). With two writers that means the column writer's debounced
save wipes `sorting`/`filters`, and the page writer's save wipes the columns. It would look
like flaky persistence, not like a bug, and it would only show up when a user changes both
within the debounce window.

**Fix: the `PUT` merges.** The handler reads the existing config and overlays only the keys
the body actually carried. Pydantic's `exclude_unset` (not `exclude_none`) distinguishes
"not writing that key" from "explicitly clearing it to null" - which is exactly the
distinction AC-A3 needs for the Clear affordance.

Rejected alternative: routing sort and filter through `DataGrid` so there is one writer. It
would force every page to pass its sort and filter state down as props into a component that
has no business knowing about them, and it inverts the existing layering. The merge is
smaller and it makes the endpoint correct for any future writer.

### 3.3 The cached config goes stale after a save (pre-existing, must be fixed here)

Found while grilling this plan, not while writing it. `useListingColumnPreferences` fetches
with `staleTime: Infinity` and its `upsertMutation` neither invalidates nor seeds
`['list-column-config', key]`. So after a save, the react-query cache still holds the
pre-save config for the rest of the SPA session. Navigate away, come back, the hook re-mounts,
reads the stale cache and applies the **old** value.

This already affects columns today. It is mostly invisible there because a user rarely
reorders columns and returns in the same session. Sort and filter are changed constantly, so
the same bug would read as "it forgot my filter" - the exact failure this feature exists to
prevent.

**Fix, in both hooks:** on a successful write, seed the cache with what was just written
rather than invalidating (we already know the value, and a refetch would race the debounce):

```ts
onSuccess: (_res, payload) =>
  queryClient.setQueryData(['list-column-config', key], {
    listing_key: key,
    config: payload,
  }),
```

Because the endpoint now merges (3.2), the seeded value must be the **merged** result the
server returned, not the partial body that was sent - otherwise seeding the column write
would drop `sorting`/`filters` from the cache and re-introduce the clobber at the client
layer. Use the `PUT` response body, which already returns the full merged config.

## 4. Design

### 4.1 Backend

**`app/schemas/list_query.py`** - extend the payload:

```python
class ListSortEntry(BaseModel):
    id: str
    desc: bool = False


class UserListColumnConfigPayload(BaseModel):
    version: int = 1
    columnOrder: Optional[List[str]] = None
    columnVisibility: Optional[Dict[str, bool]] = None
    columnSizing: Optional[Dict[str, float]] = None
    # Sort is validated: it drives an ORDER BY on the next request.
    sorting: Optional[List[ListSortEntry]] = None
    # Filters are deliberately opaque - the shape belongs to the page, and the
    # `filtersVersion` it carries is how the page detects its own stale blobs.
    filters: Optional[Dict[str, Any]] = None
    filtersVersion: Optional[int] = None
```

`sorting` is typed because it becomes an `ORDER BY` on the next request (AC-A6). `filters` is
`Dict[str, Any]` on purpose - typing it would defeat 3.1.

**`app/api/v1/list_query.py`** - `upsert_list_column_config` merges:

```python
incoming = body.model_dump(exclude_unset=True, mode="json")
existing = _config_dict(getattr(row, "config", None)) or {} if row else {}
merged = {**existing, **incoming}
# An explicitly-null key is a clear, not a no-op (AC-A3).
merged = {k: v for k, v in merged.items() if v is not None}
```

The permission gate and the `DELETE` handler are untouched (AC-A4, AC-A5).

**No migration.** The column is already `JSONB`.

### 4.2 Frontend

**New hook `lib/listing-column-preferences/useListingViewPreferences.ts`.** Sits beside the
column hook and reuses the same service and the same react-query key
(`['list-column-config', key]`), so both hooks share one fetch rather than issuing two.

```ts
useListingViewPreferences<TFilters>({
  listingKey: string,
  defaultSorting: SortingState,
  filtersVersion: number,
  debounceMs?: number,        // default 800, matching the column hook
}) => {
  sorting: SortingState,
  setSorting: OnChangeFn<SortingState>,
  filters: TFilters | null,
  setFilters: (next: TFilters | null) => void,
  isLoading: boolean,         // true until the stored config has been applied
}
```

Behaviour:
- Applies the stored `sorting` and `filters` once, on first resolve, exactly as the column
  hook does (same `appliedRef` pattern).
- Drops the stored `filters` when `filtersVersion` does not match (AC-B4).
- Debounce-writes on change, skipping the write that its own apply would otherwise trigger
  (same `skipSaveOnceRef` pattern as the column hook).
- `isLoading` stays true until applied, so the page can gate its data query (AC-B3).

**Shared toolbar `components/ui/data-grid-list-toolbar.tsx`** - extend the existing `filters`
prop with an optional active-summary, per the component-library rule (add a mode to the shared
component, never a parallel one-off):

```ts
filters?: {
  kind: 'custom';
  active?: boolean;
  activeCount?: number;
  // NEW - when present and `active`, the toolbar renders a chip stating the
  // filter in human terms with a clear affordance.
  activeSummary?: { label: string; onClear: () => void };
  content: ReactNode;
}
```

The page supplies the human-readable label (`Pending purchasing`), because only the page can
map its own filter values to words. Chip must survive 375px (AC-C4).

**Data hook `useStockInquiries`** currently takes
`DataGridApiFetchParams & { statuses?: string[] }` and has **no `enabled` option** - it is
hardcoded to always run. AC-B3's single-fetch gate therefore needs the signature widened to
accept `enabled?: boolean` and pass it through to `useQuery`. Small, but it is real work and
not a given.

**Pilot page `StockInquiriesList.tsx`:**
- Replace the local `sorting` and `statusFilter` `useState` with the hook.
- `filtersVersion: 1`, blob shape `{ statuses: string[] }`.
- Gate the data query: `useStockInquiries({ ..., enabled: !viewPrefs.isLoading })`.
- Pass `activeSummary` into the toolbar when `statusFilter.length > 0`.
- `buildDetailSearch` keeps receiving the same sorting and filter values, so the detail-page
  prev/next pager continues to walk the same set - no change needed there, but it must be
  re-verified rather than assumed.

### 4.3 What is deliberately not built

Named segments, role defaults, page-number persistence and search persistence are all out of
scope with reasons recorded in the UAC "Out of scope" table.

## 5. Phasing

| Phase | Work | Executor |
|---|---|---|
| **1 - FE against a stubbed hook** | Build the hook with an in-memory stub, wire the pilot page and the toolbar chip, tune loading / empty / filtered / cleared states, verify in a real browser at 375px and 1280px. No backend code, no tests. | `coder` in a worktree |
| **2 - BE + swap to real, test-first** | pytest for AC-A1..A6 written failing first, then the schema and merge handler. Then swap the hook's stub for the real service call. Then vitest (AC-E2, AC-E3) and the Playwright spec (AC-E4). | `coder` then `tester` |
| **3 - Review** | `reviewer` against PR-CHECKLIST and the DoD gate, then `/code-review`, then `/codex-review` for a cross-model second opinion. | `reviewer` + main session |

Branch: `feat/listing-view-memory`. Never merged to main by an agent.

## 6. Risks

| Risk | Severity | Handling |
|---|---|---|
| Two writers clobber each other | **High** - looks like flaky persistence, not a bug | The merge in 3.2, with AC-A2 pinning it from both write directions |
| Sticky filter reads as data loss | **High** - a support ticket, not a bug report | The chip is part of the feature (Group C), not a follow-up |
| Double fetch on mount | Medium - visible flash plus wasted round trip | `isLoading` gate, AC-B3 asserts exactly one request |
| Stale filter blob after a page refactor | Medium - breaks the listing for users who had a filter | `filtersVersion`, AC-B4 |
| Stale react-query cache serves a pre-save config | **High** - reads as "it forgot my filter", the exact failure this feature prevents | Seed the cache from the `PUT` response, 3.3. Pre-existing bug; fixing it is in scope. |
| Debounced write lost on fast navigation away | Low | Accepted. The next visit re-reads the last persisted value; worst case one interaction is not remembered. Not worth a beforeunload flush. |
| Reset-columns also clears sort and filter | Low | Accepted and intended - `DELETE` is "reset this listing for me". Called out so it is not later filed as a bug. |

## 7. Open questions

**Ownership: personal or role?** Still with the captain (design note, question 1). This PR
ships the personal behaviour. A role default can layer on later WITHOUT touching the rows
written today:

- The blob shape is already the contract. A role default is the same
  `{ sorting, filters, filtersVersion }` blob, keyed by `(role_id, listing_key)` instead of
  `(user_id, listing_key)`. It needs its own home - one small table, or a JSONB column on
  `roles` - which is the one migration the feature would cost.
- The resolution happens in `GET /list-query/column-config/{key}`: return
  `{**role_default, **user_row}`. The hook applies whatever the GET returns, so the client
  does not change, and a user's own row still wins ("role default + personal override").
  "Role default only" is the same GET with the user row's view keys ignored.
- The page's `filtersVersion` guard covers a role blob exactly as it covers a user blob.

Scope (sticky sort + sticky filter, no segments) and rollout (Stock Inquiries pilot) were
decided on the design note at `.lavish/list-view-memory.html`.

## 8. Rollout: SCM Sales Orders (3 Sep 2026)

Second listing, one line each per §4.3: `app/(protected)/scm/sales-orders/components/
SalesOrdersGrid.tsx` (the one grid behind both `/scm/sales-orders` and the sales-agent
record's Sales orders tab) and `useSalesOrders` (`app/(protected)/scm/hooks/useSalesOrders.ts`)
widened with the same `enabled?: boolean` gate `useStockInquiries` carries, kept OUT of the
query key.

**Shipped default sort changed alongside the rollout.** Latest Document date (`order_date`)
first, replacing the implicit `created_at desc` fallback - the captain's call, so a buyer lands
on what came in most recently rather than on insertion order. No backend change: `order_date`
was already a sortable column (`_order_by` in `app/services/scm/sales_order_service.py`).

**Blob shape**, `filtersVersion: 2` (bumped from 1 once the customer axis below moved to
`customer_code`, so an older stored blob is discarded rather than silently read as empty):

```ts
type SalesOrdersFilters = {
  status?: string; priority?: string; source?: string;
  date_from?: string; date_to?: string; customer_code?: string;
  sales_agent_id?: string; demand_class?: string; outstanding?: true;
};
```

Nine `useState` filters collapsed into this one blob, applied through a single `applyFilters`
merge helper (mirrors AC-C2's Clear contract: an empty selection stores `null`, not an empty
object). The existing "reset page on filter change" effect - previously a nine-value dependency
array - is now just `[searchQuery]`; `applyFilters`/`clearFilters` reset the page themselves.

**Pin vs remembered view.** The grid is also rendered pinned to one sales agent
(`salesAgentId` prop, `listingKey="master_data.sales_agents.view::sales-orders"` - a stable key,
not the per-agent route). A stored `sales_agent_id` from the UNPINNED list must never leak into
a pinned agent's own tab: the pin wins in `effectiveAgentId` as before, and the derived
`agentFilter` is forced to `''` whenever `pinnedToAgent`, so the stored value never reaches the
chip label either.

**Chip label.** `activeSummary.label` joins the active axes in plain words - the status
(`salesOrderStatusLabel`), priority, source, type, an `Ordered` date range (`Dates D/M/Y to
D/M/Y`), the customer's name and the agent's name resolved from `useCustomerOptions` /
`useSalesAgentOptions`, and `Outstanding qty`. An axis whose name has not resolved yet (options
still loading) is left out rather than shown blank or as a raw code/id.

**`useListStateFromUrl` narrowed.** This grid already restores list state from the detail
page's Back-to-list URL (S3-01, unrelated to this feature). Sort and every filter used to be
part of that restore; now only pagination and search are - sort and filters come from the
remembered view, which already holds what was active when the row was clicked (the debounced
write races navigation only in the accepted "lost on fast navigation away" case, PLAN §6).

**Tests.** `SalesOrdersGrid.viewMemory.test.tsx` mirrors the pilot's harness (real
`useListingViewPreferences`, stubbed transport, stubbed `useSalesOrders` and option hooks): the
gated single fetch (AC-B2/B3), the chip's plain-words label with no raw id (AC-C1), a
`filtersVersion: 0` blob discarded while the sort survives (AC-B4), a changed filter and a
changed sort each debounce-writing (AC-B5/B6) with no `page`/`query` key (AC-D1/D2), the chip's
Clear (AC-C2), and the pinned-agent case above. The seven pre-existing
`SalesOrdersList.*.test.tsx` / `SalesOrdersGrid.test.tsx` suites needed one added mock each
(`listColumnPreferencesService`, resolving `config: null` fast) so their real
`useListingViewPreferences` fetch unblocks the gate; no assertion in them was touched.

**Found AND fixed in this rollout, as a second commit (both pre-existing, and each one defeats
the feature just shipped - a null-dated row on top of "latest first"; a remembered customer
filter that filters nothing):**

- **`_order_by`'s `order_date` sort had no NULLS LAST.** Postgres defaults `ORDER BY ... DESC` to
  NULLS FIRST, so any row with a null `order_date` sorted to the very top of the new default
  view regardless of how recent it actually is - even though the same row's serializer already
  falls back to `created_at` for DISPLAY (`sales_order_service.py` line ~481). Verified against
  the dev DB: exactly one row out of 14,210 sales orders has a null `order_date` (a smoke-test
  fixture, `AC-SMOKE-SO-1`), so the practical blast radius was one row - but a manually created
  SO that skips the create-time default would hit it too, and a user who clicks the Document
  date header to sort manually already hit it, pre-dating this rollout. Fixed test-first:
  `_order_by` now returns `col.desc().nullslast()` / `col.asc().nullslast()`, tie-break by `id`
  unchanged. `tests/scm/test_sales_order_list_filters.py::
  test_order_date_desc_puts_a_null_dated_order_last_not_first` seeds three orders (one undated)
  and asserts the undated row is last in BOTH directions; confirmed red without the fix (the
  desc case put it first), green with it. The pre-existing
  `test_the_sort_is_always_made_total_by_id` needed its own assertion widened to
  `NULLS LAST`.
- **The Customer filter had been a no-op since 8 Aug 2026.** `getSalesOrders` in
  `app/(protected)/scm/services/salesOrderService.ts` sent the selected customer as
  `customer_id`, but the route (`app/api/v1/scm/sales_orders.py`) declares the param
  `customer_code`, and `useCustomerOptions`' option value IS a customer code (never an id) - so
  every customer filter on this list silently matched everything (`getSalesOrders({customerId:
  'C001', ...})` produced `?customer_id=C001`, which the route does not read at all). The
  SAME mismatch was independently present in `salesOrdersListParamsFromUrl` (the detail page's
  prev/next pager rebuilds its list query from `params.filters.customer_id`, but the URL the
  page itself writes carries `customer_code` - so the pager's own reconstruction never saw a
  customer filter either). Fixed both call sites to use `customer_code`; the FE's opaque
  `SalesOrdersFilters` blob key was renamed `customer_id` -> `customer_code` to match, with
  `FILTERS_VERSION` bumped 1 -> 2 so a blob written under the old key is discarded rather than
  silently read as empty (no real user is on v1 yet - this branch is unmerged - so the bump is
  precautionary, not a backfill). `salesOrderService.test.ts` gained a request-URL assertion;
  `SalesOrdersGrid.viewMemory.test.tsx`'s stored-config fixtures moved to `customer_code` /
  `filtersVersion: 2`. Re-verified live: picking UNIJOH DEVELOPMENT SDN BHD narrowed the grid
  from 14,210 rows to 131, all that customer.

**Browser evidence (agent-browser, 1280x800):** signed in, sidebar Supply Chain -> Orders ->
Sales Orders (session `orders-vm`). Default load sorted by Document date descending
(`sort=order_date&dir=desc`, one request, `AC-SMOKE-SO-1`'s null date no longer at the top after
the fix). Set status=Outstanding and customer=UNIJOH via the Filters popover; chip read "Clear
filter: Outstanding, UNIJOH DEVELOPMENT SDN BHD (PROJECT)" - no raw code. Opened a row, "Back to
sales orders" returned to the list with the chip and the filtered request still applied. A bare
reload of `/scm/sales-orders` (no query string) still carried the same chip and exactly one
fetch, already filtered. Clear on the chip returned the grid to the default sort with no filter
and no chip. Opened a sales-agent record's Sales orders tab: loaded with the default sort, the
pinned agent id, and none of the main list's remembered filters or agent column/filter. Second
pass (session `orders-vm2`, after the customer-filter fix): total dropped from 14,210 to 131 on
picking UNIJOH, with `customer_code=300-U003` on the wire and every visible row that customer's.
