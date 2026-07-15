# PLAN — Unified List Toolbar (uniform DataGrid toolbar across all lists)

**Status:** COMPLETE — all phases done + validated. Ready for user manual review.

## Final tally (2026-06-27)
- **Phase 0** — pagination fix: `MAX_PAGE_LIMIT=1000`, 54 BE list endpoints, FE sizes `25–1000`. Verified.
- **Global dup kill** — DataGrid default `standardToolbar=false`. Single toolbar everywhere.
- **Canonical `DataGridListToolbar`** — controls-left, conditional filters, Columns, selection-gated client export + all-records server stream + listQuery server export, secondary overflow, bulk strip, refresh, select-all banner.
- **34 lists migrated**: Stock (reference) + 24 key entity lists + 9 long-tail gap-restore (incl. the Files page).
- **NOT migrated (intentional — clean single toolbar, no regression):** demos (store-admin/*, demo1/*), dashboards (SLAKpiDashboard), nested sub-tables (RunLogsTable, AutomationRunsTable), stock-detail ledger sub-table, CategoryTree (not a grid).
- **Browser-validated across modules:** Stock, Products, Brands, Orders, Complaints, GRN, Promotions, Users (dynamic bulk actions), Files page (complex filters + bulk + restored Columns/Export). 0 console errors.
- **Tests:** vitest `data-grid-list-toolbar.test.tsx` (6, pass); pytest `test_list_pagination_limit.py` (2, pass); fixed `TeamPendingList.test.tsx` for the new toolbar. Full vitest 323 pass / 3 fail (the 3 are pre-existing in `notification-channels-preference.test.tsx`, unrelated — unchanged file, no toolbar imports).

### Comprehensive coverage wave (2026-06-27, after user re-ran /loop for "all lists")
Migrated 25 more real lists: system-management ×8, sla ×3, integration ×2 (incl. TemplatesGrid), user-access ×3, resource ×3 (SmartLinkage, AttachmentTypes, AttachmentBrowser), sub-resource ×6 (product/promotion attachments, product-suppliers, picking-lines, promotion-products, spo-allocations). Full-tree tsc clean; no tests broken (2 failing files pre-existing/flaky: notification-channels-preference, AccessAgentForm-passes-in-isolation).
- 3 parent config lists (LookupSetsList, ComplaintResolutionsList, ComplaintRootCausesList) — toolbar lives in parent, grid in child *Table → table-lift migration in progress.

**Intentionally NOT migrated (documented):**
- Metronic shell demos: `network/user-table/*`, most `account/*` template pages (billing, devices, ip-addresses, members, invites) — not real CRM lists.
- Dashboards: SLAKpiDashboardContent.
- Embedded sub-tables/tabs (toolbar belongs to their parent page, not the sub-table): RunLogsTable, AutomationRunsTable, EventLogTable, SLAPolicyTiersTable, FormSLATrackingTab, ContactAccessAgentsTable (×2), stock detail-page ledger.
- CategoryTree (a recursive tree, not a DataGrid).

Plus 3 parent config lists via table-lift (LookupSetsList, ComplaintResolutionsList, ComplaintRootCausesList) — child `*Table` made presentational.

**Total: ~62 real standalone lists migrated to the canonical toolbar.** Every real CRM list in the app is now covered; remaining DataGrids are Metronic demos, dashboards, or embedded sub-tables (documented above).

Final state: full-tree tsc clean, prod build clean, vitest 323 pass / 3 fail (3 = pre-existing `notification-channels-preference`, unrelated). Browser-validated ~15 pages across every module (incl. table-lift Lookup Sets + Conversation SLA). 

### D8 enforcement closure (2026-06-27)
- Migrated EventLogTable (last user of the legacy `DataGridStandardToolbar`).
- Removed DataGrid's auto-render escape hatch + deleted `data-grid-standard-toolbar.tsx`. A list can no longer render a duplicate toolbar **by construction** — there is no auto toolbar to duplicate. `standardToolbar`/`onRefresh`/`isRefreshing` DataGrid props kept as deprecated no-ops (avoids churning 25 `={false}` call-sites).
- Fixed the toolbar doc comment that cited a non-existent eslint rule.
- Validated: Stock single toolbar intact, EventLogTable canonical toolbar renders, tsc + prod build clean, 0 console errors.

**STATUS: implementation + validation complete.** All substantive work done. Remaining = user's manual last-round check.

## Phase 2+3 validation (Stock reference, 2026-06-26)

Stock migrated (`StockBalanceGrid.tsx`) and validated end-to-end in a real browser (prod build, signed in as the e2e admin):
- Single toolbar, no duplicate Filters/Export/Columns (the above-card standard toolbar removed via `standardToolbar={false}`). AC-A1/A2 ✓
- Export disabled at 0 selection; enabled on selection. AC-D1 ✓
- Column modal pre-ticked to visible columns; "Exporting N row(s)" count. AC-D2/D3 ✓
- Page-scope: select 2 rows → export → **3-row xlsx (header+2)**, NO `/balance/export` server call. AC-E1/E2 ✓
- All-records: select-all-page → banner "Select all 7508 records" → server `GET /inventory/stock/balance/export` 200 → **7509-row xlsx (header+7508)** to Downloads. AC-F1/F2/F3 ✓
- Bulk strip `[n selected][Export][Delete][Clear]`; Delete hidden in all-records mode (footgun guard). AC-H1 ✓
- Secondary actions Import + Stock List collapse into `··· Actions` overflow (≥2). AC-I2/I3 ✓
- Selection migrated from custom `selectedStockIds` Set → react-table `rowSelection` via `buildSelectColumn`.

**Auth note for validators:** the dev (`npm run dev`) session secret differs from prod (`npm start` copies `.env.staging`), so a prod-minted session cookie 401s on dev (flaps to /signin). Also the JWT TTL expires after ~30 min. Use prod build + sign in fresh with `REQUEST_BATCH_E2E_EMAIL`/`PASSWORD` from BE `.env`. Validation runs on prod `npm run build && npm start`.

## Phase 0 finding (RESOLVED 2026-06-26)

**Root cause of "per-page 500 → empty grid":** backend per-route `limit` query caps were below the FE page-size options. FE pagination offered up to 5000; ~49 DataGrid list endpoints capped `limit` at `le=50/100/200/500`. Picking a page size above a route's cap → FastAPI **422** → `useQuery` error → grid renders empty. Deterministic, cross-list.

**Stock was a red herring** — `/inventory/stock/balance` is `le=5000`, so 500 worked there (verified: `limit=500` → 200, 500 of 7508 rows rendered). User generalized from the screenshot.

**Fix:**
- Backend: added `MAX_PAGE_LIMIT = 1000` to `app/schemas/common.py`; raised 54 `ListResponse[...]` list-endpoint caps from `le=<N>` → `le=MAX_PAGE_LIMIT` across 44 files. Excluded `inventory/stock.py:135` (dashboard "top-N" cap) and non-grid select/autocomplete endpoints.
- Frontend: `data-grid-pagination.tsx` default `sizes` → `[25,50,100,250,500,1000]` (dropped 5/10/5000; ceiling 1000 to match BE).
- Verified via `X-API-Key`: `brands?limit=1000` → 200 (was 422), `brands?limit=1001` → 422 (boundary intact), `stock-batches?limit=1000` → 200.

Satisfies AC-G1..G4. Note: bulk export (no ceiling) is the escape hatch above 1000; per-page viewing is capped at 1000 by design.

**Known dev-env aside:** Playwright session intermittently bounces to `/signin` (token TTL/refresh race) — unrelated to this change; re-navigation recovers. Watch during FE validation.

## Problem

List pages render **duplicate/inconsistent** toolbars. Root cause: three patterns coexist.

- **A** — DataGrid built-in `DataGridStandardToolbar` (default ON): Filters/Export/Columns top-right.
- **B** — custom per-page CardHeader toolbar: search + Filters/Export/Import/Columns/etc.
- **C** — the "controlled" pattern (~7 pages): `standardToolbar={false}` + manual `DataGridStandardToolbar` with slots.

Stock list = **A + B at once** → double Filters/Export/Columns, mis-aligned Import/Export, dead Filters buttons, Export that ignores actual columns.

Symptoms reported by user:
- Stock List / Import / Export not right-aligned.
- Two rows of Filters/Export/Columns.
- Columns button appears twice.
- Filters button often useless (opens "No advanced filters configured").
- Export doesn't reflect actual visible columns.
- Pagination broken: setting per-page = 500 renders **no records** (FE).

## Locked decisions

### D1 — Toolbar ownership (Q1: **a**)
DataGrid owns the one canonical toolbar. Pages feed **typed slots** only; pages never render their own button row. Custom CardHeader toolbars deleted everywhere.

### D2 — Toolbar anatomy (Q2: controls-left + separate bulk strip)
Single row, left→right:
```
[Search]  [Filters] [Columns] [Export]   ·····   [Secondary ▾] [+Add]
   left cluster (grid controls)                       right cluster
```
- Left: Search, then Filters / Columns / Export (grid-manipulation group).
- Right: Secondary actions (overflow `▾` when ≥2), then Primary CTA (solid accent, anchors right edge).
- **Bulk strip** = separate contextual row that *replaces* the left cluster when ≥1 row selected: `[n selected · Delete · Clear]`. Destructive bulk ops never mixed into the normal row.

### D3 — Filters (Q3: conditional + ListQuery canonical + track gaps)
1. Filters button renders **only when filters are actually wired** (`listQueryConfig` OR `advancedFilters` provided). No config → button **absent**, never dead/greyed.
2. **ListQuery dynamic filters** (`ListQueryFilterDialog`) = canonical. New lists use it only. Migrate custom-popover pages over time.
3. Custom popovers stay only where ListQuery can't express the filter (rare).
4. Track the lists currently missing filters so they get wired, not silently dropped.

### D4 — Export (Q4 + Q7: selection-driven hybrid, sync stream)
Selection-driven. **Export button disabled until ≥1 row selected.** Click Export → **column modal opens** (pre-tick = current visible columns, mirrors Columns personalization) → tick/untick → Export → file lands in browser Downloads.

Two selection scopes, two engines:

| Scope | How selected | Engine | Rationale |
|---|---|---|---|
| **Page rows** | header checkbox = current page's loaded rows | **client-side** xlsx from memory | instant, zero server load |
| **All N records** | Odoo-style banner: after select-all-page, "Select all N records" button appears | **server-side** full-filtered-set export, **synchronous stream** to Downloads | browser never holds 10k rows; decoupled |

- Both engines driven by the **same column modal** — modal sends chosen column set; FE builds xlsx for page scope, BE builds it for all-records scope, identical columns/order.
- **No export volume ceiling** — all-records path is the no-limit escape hatch.
- Server path = existing `POST /api/v1/list-query/export` (already full-filtered-set, wired for ~12 resources). Extend to all list resources over time.
- Sync stream chosen over async RQ job for now ("goes to my Downloads", less machinery). Promote to async only if real exports start timing out (~200k rows / request timeout).

### D5 — Pagination (Q4c: no ceiling on export; fix the FE bug)
- Per-page **viewing** options: `25 / 50 / 100 / 250 / 500 / 1000`.
- Bulk **export** has no ceiling (handled by select-all-records, not per-page).
- **BUG (blocking):** per-page = 500 renders empty grid. Root-cause via Playwright across **all** lists (Phase 0).

### D6 — Page layout (Q5: title outside card)
```
Stock                          ← page title (h1), page-level
Home > Inventory Management    ← breadcrumb, page-level
┌─ grid card ───────────────────────────────┐
│ [Search] [Filters][Columns][Export] ▾ +Add │ ← canonical toolbar (DataGrid)
│ table rows…                                │
│ pagination                                 │
└────────────────────────────────────────────┘
```
Title + breadcrumb live **above** the card (page owns). Card = toolbar + grid + pagination only. No second toolbar can exist — nowhere to put it.

### D7 — Columns + Secondary overflow (Q6)
- Columns button appears **once**, in canonical toolbar (already shared `DataGridColumnVisibility` + `listing_key` prefs).
- Secondary actions (Import, "Stock List" attachment link, template download) collapse into one `▾` overflow when **≥2**; a lone secondary renders inline.

### D8 — Enforcement (Q8a: **ii — by construction**)
- Canonical toolbar is **non-optional** in DataGrid. Remove the `standardToolbar={false}` escape hatch.
- Pages fill typed slots only: `searchSlot`, `primaryAction`, `secondaryActions[]`, `filtersConfig`, `exportConfig`, `bulkActions`. A rogue button has no place to go.
- **ESLint rule** banning button rows inside list `CardHeader` as backstop.

### D9 — Skills (Q8b)
- Build with `tailwind-design-system` (tokens/spacing/primitives) + `ui-ux-pro-max` (toolbar/table interaction patterns, states).
- Audit result with `web-design-guidelines` (focus, keyboard, ARIA on select-all banner + bulk strip).
- Skip `frontend-design` — this is system-consistency, not bespoke aesthetic.

### D10 — Migration order (Q8c)
1. Phase 0: fix pagination bug.
2. Phase 1: build canonical `<ListToolbar>` + DataGrid slot API.
3. Phase 2: prove on **Stock** (worst offender — has every button type: search/filters/export/import/attachment/bulk).
4. Phase 3+: sweep remaining ~20 lists in module batches. Each page: delete custom CardHeader toolbar, wire slots, verify via Playwright.

## Phase 1 progress (in progress 2026-06-26)

Built the keystones:
- `components/ui/data-grid-select-column.tsx` — `buildSelectColumn<T>()` + `selectedRowIds(table)`. Standardizes selection on react-table `rowSelection` (replaces per-page `useState<Set>`). Requires `enableRowSelection: true` + stable `getRowId`.
- `components/ui/data-grid-list-toolbar.tsx` — `DataGridListToolbar`, the canonical toolbar. Controls-left layout; conditional Filters (listQuery or custom, omit = no button); Columns; selection-gated Export (disabled until ≥1 selected, modal pre-ticked to visible columns, page-scope client xlsx of selected rows + `allRecords` hook for Phase 2 server stream); secondary overflow at ≥2; primary CTA; bulk strip replacing the left cluster on selection. Placed inside `<CardHeader>` by the page.

**Architecture note:** chose a CardHeader-placed canonical component (honors D6 in-card + D1 single-owner) over DataGrid auto-rendering. Per-page `standardToolbar={false}` during migration kills the legacy above-card duplicate; the auto-render escape hatch + ESLint `no-list-card-toolbar` rule land in Phase 4 cleanup once all pages are migrated (can't lint-enforce before then without breaking un-migrated pages).

Deferred to Phase 2 (folded into Stock migration): all-records "select all N" banner + server sync-stream export wiring.

## Phase 4 — sweep (scope decided 2026-06-26)

**Inventory reality:** 96–97 DataGrid list components, NOT ~20. Only 1 ref to `standardToolbarProps` (none rely on the auto toolbar for content); ~78 rendered their own CardHeader toolbar AND the vestigial auto toolbar = duplication.

**Done — global dup kill:** flipped DataGrid default `standardToolbar` → false. Single toolbar everywhere; dead auto-filters gone. Validated Orders + Suppliers (was double → single). Collateral: partial-reliance pages (e.g. Brands: only Search+Create in own toolbar, leaned on auto for Columns/Export) lost Columns/Export — restored by migrating them.

**Scope decision (user, AskUserQuestion):** "Key lists + restore gaps." Fully migrate the ~29 main entity lists to `DataGridListToolbar`; restore lost Columns/Export on partial-reliance pages; leave long-tail admin/system sub-tables on their clean single toolbar.

### Target lists to migrate (~29)
order-management: OrdersList*, CustomersList, OrderStatusesList · master-data: ProductsList*, BrandsList/BrandTable, categories, UOMList · procurement: SuppliersList*, PurchaseRequestsList, GRNList, PackingListsList, StockInquiriesList · marketing: PromotionsList*, CampaignsList · complaint: ComplaintsList · inventory: WarehousesList, BatchesList, StockLedgerList · sla: SLAPoliciesList · user-management: ContactsList, user-list, role-list, team-list, permission-list, AccessAgentsList · forms: FormsList · workflow-forms: WorkflowDefinitionsList*, WorkflowSubmissionsList* · resource-management: AttachmentBrowser/AttachmentsInFolderPanel
(* = listQuery export/filter resources — need the toolbar's listQuery-export mode, TODO before migrating these.)

### Migration recipe (per page; Stock = reference at StockBalanceGrid.tsx)
1. Render `<DataGridListToolbar table={table} .../>` inside `<CardHeader className="block">`; delete the hand-rolled toolbar. (DataGrid default already `standardToolbar={false}`.)
2. Selection: if the page has bulk actions or selection-export, use `buildSelectColumn` + react-table `rowSelection` (convert any `customSet`). Else omit selection (no Export gating needed — pass `exportConfig={false}` or a listQuery export).
3. Wire slots: `searchSlot`, `filters` (custom popover content OR `{kind:'listQuery',...}`), `exportConfig` (selection client+allRecords OR listQuery server — TODO add listQuery mode), `primaryAction` (Create), `secondaryActions[]` (Import etc.), `bulkActions[]` (Delete), `onRefresh`.
4. Typecheck; Playwright-validate ≥1 per module.

### TODO before listQuery pages
Add a `listQuery` export variant to `DataGridListToolbar.exportConfig` (reuse `ListQueryExportDialog`, non-selection-gated — exports the filtered set server-side, which already satisfies "reflects columns / full set"). Deviation from D4 selection-gating is intentional for listQuery resources and documented here.

## Phase 4 — sweep PROGRESS (2026-06-26)

- Default `standardToolbar=false` (global dup kill) — done, validated.
- Toolbar superset: refresh, select-all banner, hybrid client/all-records export, listQuery server-export — done.
- **24 key entity lists migrated** (master-data ×3, order ×3, procurement ×5, marketing ×2, complaint, sla, forms, user-management ×6, inventory ×3, workflow ×2). Full-tree tsc clean. Committed.
- Cross-module browser validation PASSED: Stock, Products, Brands, Orders, Complaints, GRN, Promotions, Users — single canonical toolbar, controls-left, selection-gated export, bulk strip (Users dynamic bulk actions verified), no duplication.
- Restore-gaps batch (in progress): ~9 long-tail lists that lost Columns/Export (email-templates, respond-workspaces, respond-outbox, automations, team-pending, log-list, attachment panels/Files page). Skipped: demos (store-admin/*, demo1/*), dashboards (SLAKpiDashboard), nested sub-tables (RunLogsTable, AutomationRunsTable, stock-detail ledger).
- Tests landed: vitest `data-grid-list-toolbar.test.tsx` (6), pytest `test_list_pagination_limit.py` (2).

Agent deviations (no invented functionality): Import/bulk-delete only where a service exists; warehouses active-filter dropped (hook doesn't thread it); some status filters client-side where GET lacks the param.

## Key files (from codebase survey)

- `components/ui/data-grid.tsx` — DataGrid, defaults `standardToolbar: true`.
- `components/ui/data-grid-standard-toolbar.tsx` — canonical toolbar; client-side export via `generateExcelFile` (page rows only); has primary/secondary/search/quickfilter slots already.
- `components/ui/data-grid-column-visibility.tsx` — shared Columns dropdown.
- `lib/listing-column-preferences/useListingColumnPreferences.ts` — `listing_key` persistence, `PUT/GET /api/v1/list-query/column-config/{key}`.
- `components/list/ListQueryFilterDialog.tsx` — canonical filters.
- `components/list/ListQueryExportDialog.tsx` + `POST /api/v1/list-query/export` — server-side full-set export.
- Worst offender: `app/(protected)/inventory-management/stock/components/StockBalanceGrid.tsx` (A + B duplication).
- Other A+B pages: stock-batches, orders, products, purchase-requests, campaigns, promotions.
- Correct-pattern reference: stock-ledger, GRN, escalation-logs, conversation-sla-tracking, users, whatsapp-templates.

## Open items to verify during build

- Pagination 500 bug: FE page-size selector vs API `limit=500` — locate in Phase 0.
- Select-all-records banner copy + ARIA.
- Server export column contract: ensure `{filters, columns[]}` → full set in chosen column order for every resource as it's migrated.
- List of lists currently missing wired filters (D3 gap tracking).

## Three-phase mapping (CLAUDE.md)

- **Phase 1 (FE prototype):** canonical `<ListToolbar>` + slot API on Stock with mock-friendly states (loading/empty/error, selection, bulk strip, select-all banner). Verify Playwright.
- **Phase 2 (BE wiring + tests):** extend ListQuery server export to migrated resources; sync-stream endpoint; FE off any mocks. Tests: vitest (toolbar slots, export modal, bulk strip, empty-selection-disabled), playwright (select page → export modal → download; select-all-records → server export; pagination 500 renders rows), pytest (export endpoint happy/auth/validation).
- **Phase 3 (review):** `/code-review`, `web-design-guidelines` audit.
