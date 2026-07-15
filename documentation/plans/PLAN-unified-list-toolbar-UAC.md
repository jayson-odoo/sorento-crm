# UAC — Unified List Toolbar

User Acceptance Criteria for `PLAN-unified-list-toolbar.md`. Each criterion is testable (Given/When/Then). "List page" = any DataGrid-backed listing across all modules.

**Status:** Draft — to be signed off before Phase 1 build.

Legend: each AC tagged with verification path — **[vitest]** component/hook, **[pw]** Playwright FE→BE→DB, **[pytest]** backend, **[manual]** visual/manual.

---

## A. Toolbar ownership & layout (D1, D2, D6)

- **AC-A1** [pw][manual] Given any list page, When it renders, Then exactly **one** toolbar row appears — no duplicate Filters/Export/Columns buttons anywhere on the page.
- **AC-A2** [manual] Given any list page, Then the toolbar order left→right is: `Search`, `Filters` (if wired), `Columns`, `Export`, spacer, `Secondary ▾` (if any), `Primary +Add` (if any).
- **AC-A3** [manual] Given any list page, Then the Primary CTA is the only solid/accent button and sits flush to the toolbar's right edge.
- **AC-A4** [manual] Given any list page, Then page **title** and **breadcrumb** render **above** the grid card; the grid card contains only toolbar + grid + pagination (no title, no second button row inside the card).
- **AC-A5** [vitest] Given a page attempts to render its own button row inside the list `CardHeader`, Then the ESLint rule flags it (build/lint fails).
- **AC-A6** [vitest] Given DataGrid, Then there is no `standardToolbar={false}` escape hatch; the canonical toolbar always renders. Content is supplied only via typed slots (`searchSlot`, `filtersConfig`, `exportConfig`, `primaryAction`, `secondaryActions[]`, `bulkActions`).
- **AC-A7** [manual] Given a viewport from mobile→desktop, Then the toolbar stays aligned (left cluster left, right cluster right) and does not overflow horizontally; secondary/primary collapse gracefully on narrow widths.

## B. Filters (D3)

- **AC-B1** [pw] Given a list with **no** filters wired (`listQueryConfig`/`advancedFilters` absent), Then **no Filters button renders** (button is absent, not greyed, not a dead popover).
- **AC-B2** [pw] Given a list with filters wired, When Filters is clicked, Then a real filter UI opens with at least one usable control (never "No advanced filters configured").
- **AC-B3** [pw] Given a wired list using ListQuery filters, When a filter is applied, Then the grid shows only matching rows AND the request payload reflects the filter (verified via `browser_network_requests`).
- **AC-B4** [manual] Given the gap-tracking list (D3), Then every list currently showing a dead Filters button is enumerated with a decision: wire ListQuery or intentionally button-less.

## C. Columns (D7)

- **AC-C1** [pw][manual] Given any list, Then the Columns button appears exactly **once**.
- **AC-C2** [pw] Given a user hides/reorders/resizes columns via Columns, When they reload the page, Then their personalization persists (keyed by `listing_key`, via `GET/PUT /api/v1/list-query/column-config/{key}`).
- **AC-C3** [pw] Given personalized columns, When "Reset columns" is clicked, Then columns return to defaults and the saved config is deleted.

## D. Export — selection gating & modal (D4)

- **AC-D1** [vitest][pw] Given a list with **0 rows selected**, Then the Export button is **disabled**.
- **AC-D2** [pw] Given ≥1 row selected, When Export is clicked, Then a **column-selection modal opens** (export does not start immediately).
- **AC-D3** [vitest] Given the export modal opens, Then the **pre-ticked columns equal the current visible columns** (same set + order as the Columns personalization).
- **AC-D4** [pw] Given the export modal, When the user unticks a column and confirms Export, Then the downloaded file **excludes** that column and includes all still-ticked columns in grid order.
- **AC-D5** [pw] Given any export, When it completes, Then the file is delivered to the browser **Downloads** as `.xlsx`.

## E. Export — page scope (client-side) (D4)

- **AC-E1** [pw] Given the header checkbox is used to **select all rows on the current page**, When the user exports, Then the file contains exactly those page rows (count = current page row count) and no server export request is made (client-side build).
- **AC-E2** [pw] Given a subset of page rows is hand-selected, When the user exports, Then the file contains exactly the hand-selected rows.

## F. Export — all-records scope (server sync-stream) (D4, D7)

- **AC-F1** [pw] Given the user clicks the header "select all on page", Then an **Odoo-style banner appears** offering "Select all N records" (N = total filtered count).
- **AC-F2** [pw] Given the banner "Select all N records" is clicked, When the user exports, Then a **server-side** export request is made (`POST /api/v1/list-query/export`) carrying the active filters + chosen columns; the browser does **not** load all N rows into the grid.
- **AC-F3** [pytest][pw] Given an all-records export, Then the returned file contains **all rows matching the active filters** (not just the current page), in the chosen column order.
- **AC-F4** [pw] Given an all-records export of a large filtered set, When it runs, Then the file streams to Downloads (sync) without freezing the grid UI.
- **AC-F5** [manual] Given there is no hard export ceiling, Then a select-all-records export of >1 page count is not artificially truncated.
- **AC-F6** [pytest] Given the export endpoint, Then it enforces auth (401/403 on unauthenticated/unauthorized) and validates the payload (422 on bad columns/filters).

## G. Pagination (D5) — blocking bug

- **AC-G1** [pw] Given any list, When per-page is set to **500**, Then the grid renders the rows (up to 500) — **not an empty grid**. (Current bug must be fixed.)
- **AC-G2** [pw] Given the per-page selector, Then it offers `25 / 50 / 100 / 250 / 500 / 1000` and each option renders rows correctly.
- **AC-G3** [pw] Given per-page change, Then the request sends the correct `limit` and the FE renders what the API returns (verified via `browser_network_requests`).
- **AC-G4** [pw] Given the bug investigation, Then the root cause is classified FE-vs-BE and the same fix verified across ≥5 representative lists (stock, orders, products, ledger, users).

## H. Bulk actions strip (D2)

- **AC-H1** [pw][manual] Given ≥1 row selected, Then a contextual **bulk strip** replaces the left cluster showing `n selected`, a `Delete` action, and `Clear`.
- **AC-H2** [pw] Given the bulk strip Delete, When confirmed via `AlertDialog` (copy includes the count, "This action cannot be undone"), Then the rows are **hard-deleted** and the grid refreshes.
- **AC-H3** [pw] Given `Clear` in the bulk strip, When clicked, Then selection empties and the normal left cluster returns.
- **AC-H4** [manual] Given the bulk strip, Then destructive bulk actions are visually separated from normal grid controls (not interleaved).

## I. Secondary actions (D7)

- **AC-I1** [manual] Given a list with **1** secondary action (e.g. Import only), Then it renders inline (no overflow menu).
- **AC-I2** [manual] Given a list with **≥2** secondary actions (e.g. Import + Stock List + template), Then they collapse into a single `▾` overflow menu.
- **AC-I3** [pw] Given the Stock list specifically, Then Import, "Stock List" attachment link, and any template action live under the overflow `▾` — not as a separate button row.

## J. Stock list — reference migration (D10)

- **AC-J1** [pw][manual] Given the Stock list (worst offender), When migrated, Then it shows exactly one canonical toolbar with: Search, Filters (Warehouse+Status, wired), Columns, Export (selection-gated), `▾` (Import + Stock List), no duplicate buttons, and the bulk strip on selection.
- **AC-J2** [pw] Given the migrated Stock list, Then all states verified end-to-end via Playwright: loading, empty, populated, filtered, page-scope export, all-records export, per-page 500, bulk delete.

## K. Cross-list uniformity (D8, D10)

- **AC-K1** [manual] Given the full sweep complete, Then every migrated list shares the identical toolbar structure (same slot layout, same alignment, same behaviors) — verified by screenshot diff across a representative sample per module.
- **AC-K2** [vitest] Given a new list page is added later, Then it cannot render a non-conforming toolbar (slot API + ESLint enforce conformance by construction).

---

## Sign-off

- [ ] Product/user accepts A–K as the definition of done.
- [ ] Phase 0 (G) verified before Phase 1 starts.
- [ ] Each AC mapped to a concrete test (vitest/playwright/pytest) in Phase 2.
