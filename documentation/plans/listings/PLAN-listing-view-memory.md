# PLAN - Listing view memory (sticky sort + sticky filter)

**Status:** Approved, not started
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

None. Ownership (personal only), scope (sticky sort + sticky filter, no segments) and rollout
(Stock Inquiries pilot) were decided on the design note at
`.lavish/list-view-memory.html`.
