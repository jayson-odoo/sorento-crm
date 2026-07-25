# UAC — Dealer Kit: page builder, collections, PDF (S1–S3)

**Companion to:** `PLAN-dealer-kit-builder.md` (to be written)
**Status:** Pre-code. Every AC must be self-verified on the stated side(s) end-to-end before handoff.
**Scope:** S1 builder core · S2 collections + product binding · S3 PDF export. **Out of scope:** dealer-facing surface, Assembler wizard, Selection, AI design (S4+).
**Decisions:** `documentation/adr/0005` (own builder, not the shared-service template engine) · vocabulary in root `CONTEXT.md`.
**Legend:** `[BE]` backend/pytest · `[FE]` frontend/vitest+playwright · `[E2E]` full FE→BE→DB · `[MIG]` migration/data · `[T]` CI guard.

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the **real stack** (not mocks) for the side marked, per the three-phase loop.

---

## Group A — Module, schema, permissions

- **AC-A1** `[BE][MIG]` Given migration runs, Then schema `dealer_kit` exists (`CREATE SCHEMA IF NOT EXISTS`) and all module tables carry `__table_args__={"schema": "dealer_kit"}`, mirroring `scm`.
- **AC-A2** `[BE]` Given a `dealer_kit` table referencing core, Then the FK is a **normal cross-schema FK**, unqualified into `public` (`ForeignKey("products.id")`) and schema-qualified within the module (`ForeignKey("dealer_kit.page.id")`). No id-value-only references.
- **AC-A3** `[BE]` Given `app_modules_catalog`, Then one row `dealer_kit` exists with its `MODULE_MANIFEST` dependencies declared, and every router is wrapped in `Depends(require_module_enabled_with_api_key("dealer_kit"))`.
- **AC-A4** `[BE]` Given the five permission slugs `dealer_kit.page.view` / `.page.edit` / `.page.publish` / `dealer_kit.library.manage` / `dealer_kit.brochure.create`, Then each is seeded, registered in `permission_module_map`, and enforced with `require_permission` (deny-by-default; superadmin/admin bypass).
- **AC-A5** `[BE][MIG]` Given roles already provisioned before this feature, When the migration completes, Then an explicit **grant sweep** has granted the new slugs to the intended existing roles — no role silently loses access to a screen it should have (PRINCIPLES DoD #3).
- **AC-A6** `[BE][T]` Given the multi-company new-table CI guard, Then every new owned `dealer_kit` table is registered with `CompanyScopedMixin` and the leak test asserts `UNSET` scope → 0 rows and scoped query → only that company's rows.
- **AC-A7** `[E2E]` Given active company = Sorento, When a user opens the builder, Then only Sorento pages/collections/tile templates/assets are listed; switching to Mocha shows only Mocha's — a collection of Sorento products can never surface under Mocha.
- **AC-A8** `[BE]` Given uninstall of `dealer_kit`, Then dropping the schema removes pages, versions, labels, collections, tile templates and asset rows, and leaves `products`, `attachments`, `orders` and every other `public` row untouched.

## Group B — Page lifecycle: versions and labels

- **AC-B1** `[BE]` Given `dealer_kit.page_version`, Then it carries `page_id`, `version` (int), `doc` (JSONB), `commit_message`, `created_by`, `created_at`, with `UNIQUE(page_id, version)` — mirroring `ai_prompt_versions`.
- **AC-B2** `[BE]` Given a save, Then `version` = `max(version)+1` **per page_id** (never global), and an existing version row is **never updated in place**.
- **AC-B3** `[BE]` Given `dealer_kit.page_label`, Then it carries `page_id`, `label`, `version_id` FK, `updated_by`, `updated_at`, with `UNIQUE(page_id, label)`; labels are `published` and `staging`.
- **AC-B4** `[E2E]` Given a user with `page.edit` but **not** `page.publish`, When they save, Then a new version is created and `staging` may be moved, but the publish action is absent in the UI and returns 403 on the API.
- **AC-B5** `[E2E]` Given a user with `page.publish`, When they publish version N, Then the `published` label moves to N, the public render serves N, and no version row changed.
- **AC-B6** `[E2E]` Given a bad publish, When the user rolls back to version N-1, Then the label moves back and the public render immediately serves N-1 — with both versions still present.
- **AC-B7** `[BE]` Given the runtime renderer caches the published doc per page, When a label moves, Then the cache is busted and the next read serves the new version (no redeploy, no TTL wait).
- **AC-B8** `[E2E]` Given a `staging` label pointing at an unpublished version, When a reviewer opens the staging link, Then they see that version; an anonymous/unauthorised viewer does not.
- **AC-B9** `[FE]` Given the editor, When the user clicks **Preview**, Then the preview renders the **unsaved editor buffer**, not the last saved version (the known `ai_prompt` dry-run trap must not be reproduced).
- **AC-B10** `[BE]` Given a page with no `published` label, When the public render is requested, Then it 404s — never falls through to the latest version.

## Group C — Editor: sections, grid, breakpoints

- **AC-C1** `[FE]` Given the editor, When the user adds a Section, Then it renders full-width with its own background/padding controls and an empty 12-column grid inside it.
- **AC-C2** `[FE]` Given a Block in a Section, Then it stores `{colStart, colSpan, rowStart, rowSpan}` and drag/resize snap to grid cells — never to absolute pixels.
- **AC-C3** `[FE]` Given two Blocks dragged to overlap, Then they collide-push and the Section vertically compacts; overlap is impossible outside an Artboard.
- **AC-C4** `[FE]` Given a Block whose content exceeds its declared height, Then the Block grows to fit (content-driven height via measured write-back) — content is never clipped.
- **AC-C5** `[FE]` Given the doc, Then it stores `layouts: {desktop, tablet, mobile}` with column counts 12 / 8 / 4 at ≥1280 / ≥768 / <768.
- **AC-C6** `[FE]` Given a desktop layout and no manual edit at a smaller breakpoint, Then that breakpoint's layout is **derived** (reading order top-left→bottom-right, full-width stack, spans clamped) and flagged `isDerived: true`.
- **AC-C7** `[FE]` Given the user edits the mobile layout, Then `isDerived` becomes false for mobile and subsequent desktop changes **stop** re-deriving it; desktop and tablet are unaffected.
- **AC-C8** `[FE]` Given a derived layout, When the user asks to re-derive, Then it resets to derived and `isDerived` returns to true.
- **AC-C9** `[FE]` Given the runtime renderer, Then it emits **plain CSS Grid** and contains no `react-grid-layout` code — RGL is edit-time only (verified by bundle inspection or an import guard test).
- **AC-C10** `[FE]` Given an Artboard Block, Then elements inside it may be freely positioned and overlap; this is the only surface where that is possible.
- **AC-C11** `[FE]` Given the editor at ~375px and at 1280px, Then it is usable and non-clipped at both, and any modal scrolls to its submit button.

## Group D — Asset library

- **AC-D1** `[BE]` Given `dealer_kit.asset`, Then it carries `attachment_id` FK → `public.attachments`, `name`, `kind` (`logo`/`icon`/`badge`/`decorative`), `tags[]` — storage stays in `attachments`, library semantics in the module.
- **AC-D2** `[E2E]` Given a Designer uploads an SVG or raster asset, Then it appears in the library, is searchable by name and filterable by tag/kind, and is placeable into a Section or Tile Template.
- **AC-D3** `[BE]` Given a page doc referencing an asset, Then it stores the **asset id**, never a filename or URL; renaming the underlying file leaves every published page rendering correctly.
- **AC-D4** `[E2E]` Given an asset in use by a published page, When a user deletes it, Then they are warned with the usage count and must confirm (destructive-action rule) — and the published page still renders (soft reference or blocked delete, stated in the plan).
- **AC-D5** `[E2E]` Given an SVG asset, When exported to PDF, Then it renders vector-crisp at print DPI (not rasterised at screen resolution).

## Group E — Tile templates and badges

- **AC-E1** `[BE]` Given `dealer_kit.tile_template`, Then it stores a mini-grid doc with blocks bound to product fields (image, name, code, price, dimensions) plus static assets.
- **AC-E2** `[MIG]` Given `attachment_types`, Then a nullable `certification_logo_attachment_id` FK → `attachments` is added; existing rows are unaffected (null = no badge artwork).
- **AC-E3** `[MIG]` Given `attachments`, Then a nullable `valid_until` (date) is added **and appended to `__audit_columns__`**, so expiry edits appear in the audit trail.
- **AC-E4** `[E2E]` Given a Tile Template containing a **badge row** block, When a product holds an attachment whose type has a certification logo, Then that logo renders — and a product without such an attachment renders no badge in that row.
- **AC-E5** `[E2E]` Given a product's certification attachment with `valid_until` in the past, Then its badge does **not** render, on screen and in PDF.
- **AC-E6** `[E2E]` Given a badge is rendered, Then it exposes no link to, or metadata from, the underlying certificate document — `access_levels` / `is_direct_access` gating on that attachment is never bypassed by the badge.
- **AC-E7** `[FE][BE]` Given an admin screen for attachment types, Then the certification logo can be uploaded/replaced, and an expiring-soon list surfaces attachments whose `valid_until` is within a configurable window.
- **AC-E8** `[E2E]` Given one certificate attachment linked to twelve products, When its `valid_until` is updated once, Then all twelve tiles reflect it — the date lives on the document, not per link.

## Group F — Collections and product binding

- **AC-F1** `[BE]` Given `dealer_kit.collection`, Then it carries `scope` (`library` | `page`), nullable `page_id`, `name` (optional for page scope), `conditions_json`, `pinned_product_ids[]`, `excluded_product_ids[]`, `manual_order[]`.
- **AC-F2** `[BE]` Given a collection, Then membership resolves as **rule ∪ pins − exclusions**, ordered by `manual_order` then a documented fallback sort; an excluded product never appears even if the rule and a pin both match it.
- **AC-F3** `[BE]` Given `conditions_json`, Then it is evaluated by the **ported `rule_engine`** (same evaluator as promo-expiry), not a bespoke filter.
- **AC-F4** `[E2E]` Given a Designer picks products inside the editor, Then a `scope=page` collection is created silently, is invisible in the library list, and is deleted with the page.
- **AC-F5** `[E2E]` Given a page-scoped collection, When the Designer clicks **Save as reusable collection** and names it, Then it becomes `scope=library` and appears in the library — with the page still bound to it.
- **AC-F6** `[E2E]` Given a collection block on a page, Then it stores `collection_id` + `tile_template_id` + per-breakpoint column counts, and renders one tile per member product.
- **AC-F7** `[E2E]` Given a library collection bound to three pages, When a product is added to the collection, Then all three pages reflect it on next publish/render — one edit, not three.
- **AC-F8** `[BE]` Given a collection whose rule matches products in another company, Then those products are excluded by the company scope filter before the rule is applied.

## Group G — Viewer-resolved rendering

- **AC-G1** `[BE]` Given a saved page doc, Then it contains **no prices and no access decisions** — only bindings. (Inspect the JSON: a price string in a saved doc is a defect.)
- **AC-G2** `[E2E]` Given the same published page, When viewed by a staff user, a `dealer` access-level principal, and an `end_user` principal, Then each sees the price appropriate to their audience per the existing `access_levels` rules — from one document.
- **AC-G3** `[E2E]` Given a product whose `access_levels` exclude the viewer, Then it is absent from the rendered collection for that viewer — not rendered-then-hidden client-side.
- **AC-G4** `[E2E]` Given a discontinued or inactive product inside a bound collection, Then it is excluded from render (rule documented in the plan) rather than rendering as a dead tile.
- **AC-G5** `[FE]` Given the public render, Then it is server-rendered (no client-side layout pass) and the page body never scrolls horizontally at 375px.

## Group H — Print profile and Print Preview

- **AC-H1** `[BE]` Given a page, Then its print profile stores `{pageSize, orientation, margins, cover, headerFooter{left,right,pageNumbers}}` and per-section `printMode` (`include` | `exclude` | `breakBefore`), plus per-block `hideInPrint`.
- **AC-H2** `[FE]` Given block types button / CTA / filter / add-to-selection, Then `hideInPrint` defaults to true; content blocks default to false.
- **AC-H3** `[FE]` Given the editor, When the user opens **Print Preview**, Then the page renders at true paper geometry as stacked pages with visible boundaries and page numbers — using **the same print route the PDF worker renders**.
- **AC-H4** `[FE]` Given Print Preview, When the user changes page size or orientation, Then pagination re-flows live and break positions update.
- **AC-H5** `[FE]` Given Print Preview, When the user sets `breakBefore` on a section, Then that section starts a new page in the preview **and** in the exported PDF — the two agree.
- **AC-H6** `[FE]` Given the editing canvas (not preview), Then it shows **no** page-break indicators (it is not at paper width and must not imply accuracy it lacks).
- **AC-H7** `[E2E]` Given a tile that would straddle a page fold, Then `break-inside: avoid` keeps it whole on the following page.
- **AC-H8** `[E2E]` Given a screen grid that paginates or lazy-loads at N products, When printed, Then **all** member products render — a truncated PDF is a failure, not a nicety.

## Group I — PDF export

- **AC-I1** `[BE]` Given an export request, Then a `UserDownload` row is created `status=pending` with `kind` set for brochures, and an RQ task is enqueued — the request path never renders the PDF.
- **AC-I2** `[BE]` Given the worker, Then it renders via **headless Chromium print-to-PDF against the print route** — the same React runtime as the screen (no second renderer, no WeasyPrint path for this artefact).
- **AC-I3** `[BE]` Given the enqueue, Then the **viewer context** (principal, access levels, active company, page version) is snapshotted onto the job row; the worker renders from that snapshot and never falls back to a system principal.
- **AC-I4** `[E2E]` Given a dealer-audience export and a staff export of the same page, Then the two PDFs show the prices appropriate to each — proving AC-I3 end-to-end.
- **AC-I5** `[E2E]` Given a completed export, Then the download appears in **My Downloads** with filename and provider/key set, and downloads successfully via the storage router.
- **AC-I6** `[BE]` Given a render failure, Then the row is marked `failed` with the error recorded and the queue is not poisoned (mirrors `generate_complaint_pdf` / `generate_promotions_pdf` error handling).
- **AC-I7** `[E2E]` Given the exported PDF and the on-screen page at desktop width, Then content, order and styling match — same fonts, same colours, same tiles.
- **AC-I8** `[BE]` Given the worker image, Then Chromium and its runtime dependencies are present in the deployed container (documented in `DEPLOY.md`), and the export is verified in a container, not only on macOS.

## Group J — Product standards compliance

- **AC-J1** `[FE]` Given every list in this feature (pages, collections, tile templates, assets), Then it uses the shared `DataGrid` with `tableLayout: {width: 'fixed', columnsResizable: true}`, explicit `size` per column, and `truncate` + `title` for long text — no hand-rolled tables.
- **AC-J2** `[FE]` Given every dropdown in this feature, Then it uses `SearchableSelect` / `SearchableMultiSelect` — never `ui/select`, a raw `<select>`, or a hand-rolled picker.
- **AC-J3** `[FE]` Given every delete or unlink action, Then it is confirmed via `AlertDialog` / `ConfirmDeleteDialog` with the standard copy and a count for bulk actions — never `confirm()`, never one-click.
- **AC-J4** `[FE]` Given a page detail view, Then every section renders with an explicit empty state and next-step CTA — no section is hidden on missing data.
- **AC-J5** `[FE]` Given the FE, Then components call hooks → feature service → `lib/api-client`, using `extractApiError` and `buildDataGridParams` — no direct fetch/axios, no hand-rolled query strings.
- **AC-J6** `[FE]` Given any UUID in this feature, Then it is never displayed — pages, collections, assets and products resolve to human-readable identifiers.

## Group K — Tests and guards

- **AC-K1** `[T]` Given the backend, Then every new route has pytest coverage for happy path, auth denial (403 for missing permission) and validation error; every service branch is covered, test-first.
- **AC-K2** `[T]` Given breakpoint derivation, Then it is unit-tested as a pure function with a golden set written **before** the implementation (deterministic engine rule).
- **AC-K3** `[T]` Given collection resolution (rule ∪ pins − exclusions, ordering), Then it has a golden-set test written before the implementation.
- **AC-K4** `[T]` Given FE hooks and components, Then vitest covers loading / empty / error / data states for each new component.
- **AC-K5** `[E2E]` Given Playwright, Then one spec drives sidebar → builder → create page → add section → bind a collection → publish → view public render → export PDF → appears in My Downloads, asserting the expected `/api/v1/*` calls.
- **AC-K6** `[T]` Given pytest fixtures for this feature, Then all cleanup is **scoped to marker rows** and symmetric before+after — no unscoped `DELETE FROM` against the local prod-copy database.
- **AC-K8** `[T]` Given backend tests, Then they run on **Postgres only** (no sqlite substrate); committing tests use a private `zzt_` scratch schema, and CI's `bootstrap_env` stamps the alembic head so a dual-head migration fails the job.
- **AC-K7** `[E2E]` Given the whole feature, Then it is verified from the user's perspective by real sidebar clicks at **375px and 1280px**, against a **prod build** (`npm run build && npm start`) before handoff.
