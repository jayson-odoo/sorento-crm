# PLAN: Standardize list→detail record navigation (prev/next "X / Y" pager)

**Status:** Approved - decisions locked, Phase 1 = Complaints
**Owner:** jayson
**Slug:** record-navigation-standardization

### Locked decisions (user, this session)
- **D1 - Rollout:** incremental, **Complaints first** (Phase 1 = shared FE hook + backend `compute_neighbours` helper + complaints `/neighbours` endpoint + complaints detail wired + tests). Then sweep the remaining 13 resource-by-resource.
- **D2 - Out-of-filter record:** if the opened record is NOT in the active filtered set (deep link, or edited out), `/neighbours` **falls back to the unfiltered (default-sorted) set** so prev/next still works and the total reflects the unfiltered count. Never a dead pager.
- **D3 - Boundaries:** **circular wrap-around** - Next on the last wraps to the first, Prev on the first wraps to the last. `compute_neighbours` returns wrapped `prev_id`/`next_id`; both chevrons always enabled unless total ≤ 1.

---

## 1. Problem statement (verified)

On a detail page, the chevron pager ("‹ X / Y ›") that walks to the previous/next record does **not** respect the active list filter/search/sort. Reproduction provided by the user:

- Complaints list, filter `complaint_number = "04"` → 23 rows.
- Open a row → detail pager reads **"6 / 44"**, not "… / 23".
- The "44" is the count of the first unfiltered page (capped at 100) of *all* complaints; the "6" is the record's index within that unfiltered, differently-sorted set.

Root cause is structural and shared, not complaint-specific: most detail pages build their navigation set with a **fixed, hard-coded list query** that throws away the user's active filter/search/sort. A few pages thread *some* state but still display the wrong total.

The user's desired mechanism (from prior systems): **every prev/next is a backend call** scoped to the exact filtered+sorted+searched set the user navigated from, and the displayed total equals the filtered result count.

---

## 2. Investigation findings (file:line anchors)

### 2.1 Shared component - `RecordNavigation`

`sorento_crm_frontend/components/common/RecordNavigation.tsx`

Already a **dual-mode** component (good foundation - we keep it):

- **IDs mode** (`RecordNavigationIdsProps`, lines 9-21): caller passes `prevId`, `nextId`, optional `currentIndex` + `totalCount`. Renders `"{currentIndex+1} / {totalCount}"`. This is exactly the shape a backend-driven design needs. **Currently used by zero pages.**
- **List mode** (`RecordNavigationListProps`, lines 23-38): caller passes `currentId` + `items: {id}[]`, optional `circular`, `totalCount`, `pageItemOffset`. Computes prev/next via `items.findIndex` (lines 83-102), displays `pageItemOffset + idx + 1 / (totalCount ?? items.length)` (lines 81-86). **This is the flawed path every real page uses today.**

The counter logic (lines 113-121) already supports a `positionUnknown` state (" -  / N" when the current id isn't in the fetched page). That's a symptom of the core bug: the page the record lives on often isn't the page that was fetched.

### 2.2 The neighbours hook exists but is unused

`sorento_crm_frontend/hooks/useRecordNeighbours.ts` - generic hook that GETs a backend `…/neighbours?id=<id>&<filters>` endpoint and returns `{ prev_id, next_id }` (lines 6-45). **It is imported nowhere** except its own definition. Purchase-request detail references a `'purchase-request-neighbours'` query key in `invalidateQueries` calls (`PurchaseRequestDetail.tsx:372,416,1227,…`) but never actually fetches it - those invalidations are dead. **No backend `/neighbours` endpoint exists** (`grep -rn "neighbours\|neighbors" sorento_crm_backend/app` → nothing). So the "backend-driven" path was scaffolded and abandoned.

### 2.3 Every detail page with a prev/next pager - current wiring

| Resource | Detail file | Nav source query | Threads filters? | Counter shown | Behavior |
|---|---|---|---|---|---|
| **Complaints** | `complaint-management/complaints/components/ComplaintNavigation.tsx` (rendered by `ComplaintDetail.tsx:394`) | `useComplaints` with **hard-coded** `{pageIndex:0, pageSize:100, sorting:[{complaint_date desc}], searchQuery:''}` (lines 17-24) | **No** | none passed → falls back to `items.length` (≤100) | **BROKEN** - "6 / 44" |
| **Purchase requests / Sponsorship forms** | `procurement-management/purchase-requests/components/PurchaseRequestDetail.tsx:128-140,595` | `usePurchaseRequests` with hard-coded `{pageSize:50, sorting:[created_at desc], searchQuery:''}` (only `requestType` varies) | **No** | none | **BROKEN** |
| **Stock inquiries** | `procurement-management/stock-inquiries/components/StockInquiryDetail.tsx:69-72,451` | hard-coded `{pageSize:50, created_at desc, searchQuery:''}` | **No** | none | **BROKEN** |
| **GRN** | `procurement-management/grn/components/GRNDetail.tsx:69-72,127` | hard-coded `{pageSize:50, picking_date desc, ''}` | **No** | none | **BROKEN** |
| **Packing lists** | `procurement-management/packing-lists/components/PackingListNavigation.tsx` | hard-coded `{pageSize:100, created_at desc, ''}` | **No** | none | **BROKEN** |
| **Suppliers** | `procurement-management/suppliers/[id]/components/SupplierDetail.tsx:24-27,76` | hard-coded `{pageSize:100, created_at desc, ''}` | **No** | none | **BROKEN** (often looks fine - small dataset) |
| **Customers** | `order-management/customers/components/CustomerDetail.tsx:24-27,74` | hard-coded `{pageSize:100, created_at desc, ''}` | **No** | none | **BROKEN** |
| **Promotions** | `marketing-management/promotions/components/PromotionDetail.tsx:95-98,537` | hard-coded `{pageSize:100, created_at desc, ''}` | **No** | none | **BROKEN** |
| **Forms (definitions)** | `forms-management/forms/[id]/components/FormDetail.tsx:37-40,156` | hard-coded `{pageSize:100,…}` but **passes** `totalCount={pagination.total}` (line 159) | **No** (filters not threaded) | true total, but nav still limited to first 100 ids | **PARTIALLY BROKEN** - total can read right by luck, neighbours wrong past page 1 / under filter |
| **Access agents** | `user-management/access-agents/components/AccessAgentDetail.tsx:116-119,212` | hard-coded `{pageSize:100,…}` | **No** | none | **BROKEN** |
| **Conversation SLA tracking** | `sla-management/conversation-sla-tracking/components/ConversationSLATrackingDetail.tsx:103-106,350` | hard-coded `{pageSize:100,…}` | **No** | none | **BROKEN** |
| **Attachments** | `resource-management/attachments/components/AttachmentDetail.tsx:200-203,272` (+ `AttachmentDetailModal.tsx`) | hard-coded `{pageSize:100, uploaded_at desc, ''}` | **No** | none | **BROKEN** |
| **Orders (delivery orders)** | `order-management/orders/components/OrderDetail.tsx:35-50,111-120` | `useOrders` with **listNav threaded from URL** via `orderListNavQuery` util; `totalCount={navPageSize}`, `circular={false}` | **Yes (filters)** but pageSize-capped | shows **pageSize as total** (e.g. "/50"), not filtered total | **PARTIALLY BROKEN** - correct within one page only; total is wrong (shows page size) |
| **Products** | `master-data-management/products/[id]/components/ProductDetail.tsx:35-58,123-128` | `useProducts` with **filters threaded from URL search params** (search/category/brand/status/sort/page/pageSize); navigates with full query string preserved (lines 71-77) | **Yes (filters)** | none passed → `items.length` (≤500) | **CLOSEST TO CORRECT but still list-mode** - respects filters, but total = fetched-page length and nav can't cross pages |

Other `RecordNavigation` importers that are **modal/in-page selectors, not list→detail pagers** (out of scope, leave alone unless trivial): `CustomerForm.tsx`, `PromotionForm.tsx`, `AccessAgentForm.tsx`, `ProductForm.tsx`, `SupplierForm.tsx`, `inventory-management/stock/[productId]/[warehouseId]/page.tsx`, `integration-management/integration-logs/[id]/page.tsx`, `user-management/contacts/[id]/page.tsx`, `user-management/users/[id]/layout.tsx`. Confirm during Phase 2 sweep whether any of these are genuine list pagers.

### 2.4 How Products "looks right" - the honest answer

Products is **not** using the backend-driven mechanism. It is still **list-mode**: it fetches a page of products (default `pageSize:50`, capped at 500) and the pager indexes into that array. It looks correct because:

1. It **threads the active filters/sort/search via URL search params** (`ProductDetail.tsx:36-55`) - the list page links into the detail with the query string, and the detail re-runs the *same* list query. So the *set* it walks matches the list.
2. It preserves the query string when navigating between records (lines 72-77).

But it shares two latent flaws with everyone else: (a) no true `totalCount` is passed, so the counter (if shown) would be the fetched page length, not the filtered total; (b) navigation cannot cross a page boundary - past record 50/500 the neighbour is missing. Products escapes notice because product datasets are small and users rarely page deep. **Products is the right *contract* (filters in the URL) with the wrong *engine* (client array).**

### 2.5 How complaints produces "6 / 44" specifically

- `ComplaintsList.tsx` keeps filter state in local React state: `searchQuery`, `assignedToFilter`, `statusFilter`, `sorting`, `pagination` (lines 45-72). Row click does `router.push('/complaint-management/complaints/${complaintId}')` (line 84) - **bare URL, zero filter params carried over.**
- `ComplaintNavigation` then fetches `useComplaints({pageIndex:0, pageSize:100, sorting:[complaint_date desc], searchQuery:''})` - unfiltered, fixed sort.
- Result: 44 = number of complaints in the first 100 of the *unfiltered* set actually returned (or the all-complaints count if ≤100); 6 = the record's index in that wrong set. The user's filtered 23 never enters the calculation.

### 2.6 Backend list endpoints + the list-query registry

- **Complaints list:** `app/api/v1/complaints/complaints.py:199-231` `GET /` → `ComplaintsService.list_complaints(...)` (`app/services/complaints_service.py:343-486`). The service builds a single filtered+sorted SQLAlchemy query `q` (filters lines 362-400, sort lines 408-422), then `total = q.count()` (424) and `q.offset(...).limit(...)` (426). Auth: `Depends(get_current_user_or_api_key)`; module guard `require_module_enabled_with_api_key("complaints")` at mount (`api/v1/__init__.py:98-101`).
- **Same shape** across orders, suppliers, promotions, stock-inquiries, purchase-requests, products: a service method that assembles a filtered/sorted query then paginates. The **filter/sort logic is the reusable asset** - a neighbours endpoint must run the *identical* query and compute position/neighbours from the ordered result, not re-implement filtering.
- **`app/services/list_query_registry.py`** is metadata-only: it maps `resource_key → {view_slug, export_slug, serializer, model, compile_prefix}` (lines 56-140). It does **not** execute the list query or own the filter/sort logic - that still lives per-service. So it cannot, as-is, power a generic neighbours endpoint; the actual filtering is not centralized there.

---

## 3. Recommended design

### 3.1 Mechanism: backend-driven neighbours, filters carried in the URL

**Carrier for filter state = URL search params on the detail route.** The detail page is a separate route (`/{module}/{id}`), so the only DRY, refresh-safe, shareable way to know "which filtered set did the user come from" is to put the list query into the detail URL - exactly what Products/Orders already do. We standardize that.

Each navigation (and the initial detail open) calls a backend endpoint that, **for a given record id within the supplied list-query**, returns:

```jsonc
// GET .../neighbours?id=<uuid>&<list-query params>
{
  "total":  23,        // count of the filtered/sorted set
  "index":  6,         // 1-based position of <id> within that set
  "prev_id": "…uuid…", // null if first
  "next_id": "…uuid…"  // null if last
}
```

Rendered via `RecordNavigation` **IDs mode** with `currentIndex = index - 1`, `totalCount = total`, `prevId`, `nextId`. No client-side array, no page-boundary problem, total is always the true filtered count.

### 3.2 Design A vs Design B

- **Design A - position+neighbours endpoint (RECOMMEND).** One GET per resource (or one generic, see §3.4) that takes the same query/filter/sort params the list takes plus `id`, runs the existing filtered+sorted query, and returns `{total, index, prev_id, next_id}`. Computed with window functions or a bounded scan (see §3.5). Pros: single round-trip per navigation, exact total, no offset drift, matches the already-built `useRecordNeighbours`/IDs-mode shapes. Cons: must thread the full filter param set to the endpoint (mitigated by reusing the list param parsing).

- **Design B - cursor/offset.** Detail receives `offset` of the current row; prev = offset-1, next = offset+1; fetch single rows by offset. Pros: trivial endpoint. Cons: **offset drift** - inserts/deletes/sort ties between list view and navigation silently shift neighbours; `total` still needs a separate count; equality/duplicate sort keys make offsets ambiguous; doesn't survive the record being filtered out. Rejected.

**Decision: Design A.** It's the mechanism the user described, the FE primitives already exist for it (`RecordNavigation` IDs mode + `useRecordNeighbours`), and it's correct under concurrent mutation.

### 3.3 Frontend: one code path

1. **Keep `RecordNavigation`** as-is (dual-mode) but make **IDs mode the standard** for list pagers. Add an optional `isLoading` prop to render a neutral counter while neighbours resolve (avoids a flash of " -  / N").
2. **Generalize `useRecordNeighbours`** to return `{ prevId, nextId, index, total }` (rename response fields to camelCase in the hook boundary; backend stays snake_case). Keep `enabled: !!currentId`.
3. **Per resource, add a tiny `useXxxNeighbours` wrapper** (or call `useRecordNeighbours` directly) that maps the resource's list query into the endpoint params using `buildDataGridParams(params, extraFilters)` - the **same** call the list page already uses - so filter serialization is defined once.
4. **List → detail URL threading (DRY):** each list page already builds its DataGrid params with `buildDataGridParams`. On row click, serialize the *current* list query into the detail URL search string (Orders' `orderListNavQuery` util is the template - generalize it to a shared `lib/listNavQuery.ts` `buildDetailSearch(params)` / `parseDetailSearch(searchParams)` pair). The detail page parses the same params and feeds them to the neighbours hook and to the "Back to list" link.
5. **Replace** each resource's bespoke nav component (`ComplaintNavigation`, `PackingListNavigation`) and inline list-mode `RecordNavigation` usages with: parse URL params → `useXxxNeighbours` → `RecordNavigation` IDs mode. Delete the hard-coded `{pageSize, sorting, searchQuery:''}` blocks.

FE layering respected: UI → `useXxxNeighbours` hook → feature service (`getXxxNeighbours`) → `lib/api-client`/`apiFetch` → backend. Use `buildDataGridParams` for the query string; no hand-rolled `URLSearchParams`.

### 3.4 Backend: generic endpoint vs per-resource

**Recommendation: per-resource neighbours endpoint that reuses the existing service query builder, with a shared helper for the position math.**

Rationale: the filter/sort logic is *not* centralized (the registry is metadata-only, §2.6); each resource's `list_*` service owns its `WHERE`/`ORDER BY`. Re-implementing all of that generically (Design "one endpoint via registry") would duplicate or destabilize bespoke filters (e.g. complaints' 18-column search, orders' `advancedFilter`, PR's `request_type`). Instead:

- Add a shared helper `app/services/record_neighbours.py::compute_neighbours(query, model, current_id) -> {total, index, prev_id, next_id}` that takes an **already-filtered-and-ordered** SQLAlchemy `Query` plus the model and the id, and does the position math (§3.5). One implementation, fully tested.
- In each resource service, add a thin `neighbours(...)` method that builds the **same** `q` as `list_*` (extract the filter+sort block into a private `_build_list_query(...)` so `list_*` and `neighbours` share it - removes duplication and guarantees they can't drift) and calls `compute_neighbours(q, Model, id)`.
- In each router, add `GET …/neighbours` next to `GET /` with the **same query params and the same auth dependency** (`get_current_user_or_api_key` + module guard already applied at mount). Return `{total, index, prev_id, next_id}`.

This keeps each resource's filtering authoritative, centralizes only the generic math, and is incremental (ship resource-by-resource).

### 3.5 Position math (the shared helper)

Given the filtered+ordered query `q` over `Model` with a stable order, compute without materializing the whole set:

- `total = q.count()`.
- Wrap `q` in a subquery exposing `row_number() over (<same order>)` and `id`; select the row where `id = current_id` to get `index`; select `id` at `index-1` and `index+1` for `prev_id`/`next_id`. (Single CTE/window query; falls back to two bounded `LIMIT 1` queries - "first row after current in order" / "first row before current in reversed order" - if window composition with the existing `order_by` is awkward.)
- **Tie-breaker:** every `ORDER BY` used for neighbours MUST be deterministic. Append `Model.id` (or `created_at, id`) as a final sort key in `_build_list_query` so `row_number` is stable and prev/next are unambiguous. Verify each resource's existing sort already has, or now gets, a deterministic tail.
- Record filtered out / not in set → `index = null`, `prev_id`/`next_id` = best-effort `null` (FE shows " -  / total", IDs mode already handles a null counter).

---

## 4. Three-phase breakdown (per CLAUDE.md)

### Phase 1 - FE prototype (one resource: Complaints), mock backend

- Generalize `RecordNavigation` usage to IDs mode for complaints; add `isLoading` prop.
- Build `useComplaintNeighbours` calling a **stubbed** `getComplaintNeighbours` that returns synthetic `{total, index, prev_id, next_id}` (and the edge cases: first record `prev_id:null`, last record `next_id:null`, filtered-out `index:null`).
- Thread complaints list filter state into the detail URL: extend `ComplaintsList` row-click to serialize its current DataGrid params (search/assignee/status/sort/page) via the new shared `lib/listNavQuery.ts`; detail page parses them.
- **Document the contract** at the top of `complaintService.ts` (request params = list params + `id`; response `{total, index, prev_id, next_id}`; status enums N/A).
- Verify in browser via Playwright MCP: complaints sidebar → list → filter `complaint_number = 04` → open a row → assert pager shows "k / 23" (mock wired to 23) → click next/prev → assert neighbour id. Screenshot golden path + first/last/filtered-out.
- **No backend, no tests yet** (UI shape may shift on review).

### Phase 2 - BE wiring + remaining resources + tests

Backend:
- `app/services/record_neighbours.py::compute_neighbours(...)` (shared math, §3.5).
- Complaints: extract `_build_list_query` in `complaints_service.py`, add `neighbours(...)`, append deterministic sort tail; add `GET /complaints-management/neighbours` in `complaints.py` mirroring `get_complaints` params + auth.
- Then per resource (orders, purchase-requests/sponsorship, stock-inquiries, products, suppliers, customers, promotions, GRN, packing-lists, forms, access-agents, conversation-sla, attachments): same pattern. Order by user-visible breakage priority: complaints → purchase-requests/sponsorship → stock-inquiries → orders → products → the rest.

Frontend:
- Generalize `useRecordNeighbours` → `{prevId,nextId,index,total}`; add shared `lib/listNavQuery.ts` (promote Orders' `orderListNavQuery`).
- Replace each resource's hard-coded nav block / bespoke nav component with: parse URL → `useXxxNeighbours` → `RecordNavigation` IDs mode. Delete `ComplaintNavigation`/`PackingListNavigation` internals (or convert to thin wrappers). Remove dead `'*-neighbours'` invalidations in `PurchaseRequestDetail.tsx` or wire them to the real query key.
- Make every list page thread its params into the detail URL on row click + preserve query string when navigating between records and on the "Back to list" link.

**Tests (land here, not deferred):**
- **vitest** (`sorento_crm_frontend/`):
  - `RecordNavigation` IDs mode: renders `index/total`, disables prev when `prevId==null`, disables next when `nextId==null`, " -  / total" when `index==null`, loading state.
  - `useRecordNeighbours`: builds the right query string from list params via `buildDataGridParams`, disabled when no `currentId`, maps snake→camel.
  - `lib/listNavQuery.ts`: round-trip `build → parse` preserves filters/sort/search.
  - At least the complaints `useComplaintNeighbours` wrapper + the refactored `ComplaintNavigation`.
- **pytest** (`sorento_crm_backend/`): for the complaints neighbours endpoint (and a 2nd resource as a second proof):
  - happy path: middle record → correct `prev_id`/`next_id`/`index`/`total`.
  - **filter respected:** with `query=04` the `total` equals the filtered count and neighbours stay within the filtered set.
  - first record → `prev_id:null`; last record → `next_id:null`.
  - sort respected: `sort`/`dir` change reorders neighbours.
  - record filtered out → `index:null`.
  - **auth denial:** no token / no API key → 401/403.
  - Service-level test for `compute_neighbours` math (incl. deterministic tie-break with equal sort keys).
- **Playwright** (`sorento_crm_frontend/e2e/`): one spec - sidebar → Complaints → filter `complaint_number = 04` → open a row → assert pager total equals the filtered list count (read both from the UI) → assert `browser_network_requests` shows `GET …/complaints-management/neighbours?...&query=04` → click next → assert URL/id is the correct neighbour and counter increments.

Re-verify with Playwright MCP against the live stack (FE :3000, BE :8000); states must match the prototype with real data.

### Phase 3 - Code review

`/code-review` (or `ultra` given breadth) on the combined branch; address with `--fix`/`/simplify`; confirm PR-CHECKLIST items + "Phase 1 screenshot present, Phase 2 added vitest+playwright+pytest, contract doc matches shipped".

---

## 5. Rollout / migration note

- **Backward-compatible transition.** `RecordNavigation` keeps both modes; list-mode stays functional so un-migrated pages don't break mid-rollout. Migrate **resource-by-resource**: ship Complaints end-to-end first (highest visible breakage), then proceed down the priority list, each resource a self-contained FE+BE+tests slice.
- **No DB migration required.** Add a deterministic sort tail in the query builder only (no schema change). If any resource lacks a non-null stable secondary sort column, prefer `id` as the tie-breaker - no migration needed.
- After all list pagers are migrated to IDs mode, schedule a cleanup PR to remove list-mode from `RecordNavigation` (and `pageItemOffset`, `positionUnknown` branches) so there is exactly one path.
- **RBAC / module guards:** neighbours endpoints reuse each resource's existing auth dependency and module-guard mount - no new permission slugs. Confirm `EXTERNAL_API_KEY_ACT_AS_USER_ID` path still works for any externally-consumed list (MCP is read-only and unaffected - it wraps list GETs, not neighbours).
- **list_query_registry:** no change required (it's metadata-only and not on this path). If a future generic endpoint is desired, that's a separate effort to first centralize filter/sort there.
- **Embedding pipeline / worker / RQ:** no impact (pure read path).

---

## 6. Inventory table (every list→detail pager, current state, change required)

| # | Resource (list) | Detail / nav file | Current | Change required |
|---|---|---|---|---|
| 1 | Complaints | `ComplaintNavigation.tsx` + `ComplaintDetail.tsx:394` | BROKEN (unfiltered pageSize:100) | List threads params to URL; replace with `useComplaintNeighbours` + IDs mode; BE `/complaints-management/neighbours` |
| 2 | Purchase requests / Sponsorship forms | `PurchaseRequestDetail.tsx:128-140,595` | BROKEN (pageSize:50, no filters) | Thread URL params; neighbours hook + IDs mode; BE neighbours (with `request_type`); remove dead `*-neighbours` invalidations |
| 3 | Stock inquiries | `StockInquiryDetail.tsx:69-72,451` | BROKEN | Same pattern |
| 4 | GRN | `GRNDetail.tsx:69-72,127` | BROKEN | Same pattern |
| 5 | Packing lists | `PackingListNavigation.tsx` | BROKEN | Same pattern (replace bespoke nav) |
| 6 | Suppliers | `SupplierDetail.tsx:24-27,76` | BROKEN (looks ok, small data) | Same pattern |
| 7 | Customers | `CustomerDetail.tsx:24-27,74` | BROKEN | Same pattern |
| 8 | Promotions | `PromotionDetail.tsx:95-98,537` | BROKEN | Same pattern |
| 9 | Forms (definitions) | `FormDetail.tsx:37-40,156-159` | PARTIAL (true total, no filters, page-capped nav) | Thread filters; switch to neighbours/IDs mode |
| 10 | Access agents | `AccessAgentDetail.tsx:116-119,212` | BROKEN | Same pattern |
| 11 | Conversation SLA tracking | `ConversationSLATrackingDetail.tsx:103-106,350` | BROKEN | Same pattern |
| 12 | Attachments | `AttachmentDetail.tsx:200-203,272`, `AttachmentDetailModal.tsx` | BROKEN | Same pattern (note: filters incl. linkage/folder) |
| 13 | Orders (delivery orders) | `OrderDetail.tsx:35-50,111-120` + `orderListNavQuery` util | PARTIAL (filters threaded, but total=pageSize, page-capped) | Promote util to shared `lib/listNavQuery`; switch to neighbours/IDs mode for true total + cross-page nav |
| 14 | Products | `ProductDetail.tsx:35-58,123-128` | CLOSEST (filters via URL, list-mode) | Switch list-mode → neighbours/IDs mode for true total + cross-page; reuse its URL-threading as the template |

**Out-of-scope (verify in Phase 2 sweep - these import `RecordNavigation` but appear to be modal/in-page selectors, not list→detail pagers):** `CustomerForm`, `PromotionForm`, `AccessAgentForm`, `ProductForm`, `SupplierForm`, `inventory-management/stock/[productId]/[warehouseId]/page.tsx`, `integration-management/integration-logs/[id]/page.tsx`, `user-management/contacts/[id]/page.tsx`, `user-management/users/[id]/layout.tsx`. If any is a genuine list pager, fold it into the rollout.

---

## 7. Contract (locked in Phase 1)

```
GET  /{module}/{resource}/neighbours
Query params: id=<uuid>  +  the exact same params the resource's list GET accepts
              (page/limit are ignored for neighbours; query/sort/dir/<filters> are used)
Auth:  same dependency as the list GET (Bearer JWT or X-API-Key), same module guard
200:   { "total": int, "index": int|null, "prev_id": uuid|null, "next_id": uuid|null }
401/403: unauthenticated / module disabled
422:   invalid params
```

FE hook surface: `useRecordNeighbours(apiPath, currentId, listParams) → { prevId, nextId, index, total }`, params built with `buildDataGridParams`.

---

## 8. Open decisions - RESOLVED

1. **Counter format** - "X / Y" (1-based). Out-of-filter → fall back to unfiltered set (D2), never a dead pager.
2. **Boundaries** - circular wrap-around (D3).
3. **Rollout** - incremental, Complaints first (D1).
4. **Out-of-scope importers** - the ~9 other `RecordNavigation` importers are modal/selector uses, not list pagers; leave untouched (verify in Phase 1 review).

---

## 9. User Acceptance Criteria (UAC)

Phase 1 scope = **Complaints**. UAC-1..13 are the acceptance bar; the same criteria become the template for each subsequent resource in the sweep.

### Filtered navigation
- **UAC-1** On the Complaints list, applying a filter/search (e.g. DO Number "04" → N rows) then opening a record shows a pager whose **total equals N** (the filtered count) - NOT the unfiltered total. (Reproduces & fixes the "6 / 44 instead of /23" bug.)
- **UAC-2** The pager **index** is the record's 1-based position within the filtered **and sorted** set.
- **UAC-3** **Next** navigates to the next record in the filtered+sorted order; **Prev** to the previous. The landed record is correct (assert by visible identifier).
- **UAC-4** The list's **active sort** (column + direction) is honored by prev/next order.
- **UAC-5** **All active list filters** are honored together: free-text search, status filter, assignee filter (and any complaint-specific filters).

### Boundaries & edge cases (D2/D3)
- **UAC-6** **Circular wrap** - Next on the last record lands on the first; Prev on the first lands on the last. Both chevrons enabled whenever total > 1.
- **UAC-7** **Single-record set** (total = 1) → both chevrons disabled; pager reads "1 / 1".
- **UAC-8** **Out-of-filter / deep-link** - opening a record that is not in the active filtered set (or that an edit pushed out) **falls back to the unfiltered, default-sorted set**: pager still works and total = unfiltered count. No dead pager.
- **UAC-9** **Cross-page** - navigation is a backend call, so a record at position > one page (e.g. #501 of a 600-row filtered set) navigates correctly with no client-side page-boundary gap.

### Plumbing & non-regression
- **UAC-10** Returning to the list from detail **preserves the filter/search/sort state** (carried via URL search params; round-trips through `buildDataGridParams`).
- **UAC-11** **Auth** - the `/neighbours` endpoint enforces the same permission as the complaints list view; an unauthorized principal gets 403.
- **UAC-12** **Efficiency** - neighbours resolve via a bounded query (position + neighbour ids), not by loading the full result set into memory; one round-trip per navigation.
- **UAC-13** **No regression** - opening a complaint with **no active filter** behaves as before: full set, correct total, correct neighbours.

### Quality bar (reviewer gate, internal)
- All three suites green: **pytest** (UAC-1/5/6/8/11/13 + first/last edges), **vitest** (`useRecordNeighbours` hook + `RecordNavigation` IDs mode), **Playwright** (UAC-1→3 end-to-end: filter "04" → open → assert "X / N" = filtered count → Next → correct neighbour).
- Conforms to `documentation/ARCHITECTURE-RULES.md` (extractApiError, buildDataGridParams, hook→service→api-client layering) and `documentation/reference/ADR-PRODUCT-STANDARDS.md`.
- The dead `useRecordNeighbours` scaffold is either completed or removed - no dead code left.
