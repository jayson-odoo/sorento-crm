# PLAN: Spec sheet tab v2, saved spec sheets list + PDF-style viewer (SPEC-SHEET-V2)

**Status:** Built, PR #2124 ready for review (mock v2 approved 3 Nov 11:45). Reviewer READY (last kill test fixed), security
PASS, cloud browser pass done (one defect found and fixed: edit route double-encoded the page key). Waiting on CI
label, owner hand test, and #2126's export image cap. Track: L.
Card: `CARD-spec-sheet-v2-03nov.md`.
Track: L (new table migration, new routes). Builds on #2103 (`PLAN-ps-spec-sheet-02nov.md`).
UAC: `spec-sheet-v2-03nov-acceptance-criteria.md` (after the mock is approved).

## Owner feedback (3 Nov ~11:35, verbatim)

"the selection of 4 things is very not compliant with the system design. The spec sheet needs a
table listing the spec sheets created; when I click Create spec sheet I can select the revision.
Now the revision must be signed back by the customer, right? Actually when we send to the customer
we already send the catalogue, so we shouldn't need to wait until the customer signs back. When I
view the spec sheet it should be a natural PDF scrolling motion, with the ability to further edit /
amend using the designer we have."

## Process

1. Behaviour card (crew-ask): rules, real examples, edge cases, questions.
2. Lavish mock (static HTML, app design system) as crew-ask; build only after owner OK.
3. Red-first tests, coder, reviewer + security review (new table), browser pass, hand test.

## Owner build order (3 Nov 11:45, mock v2 approved)

"ok, reuse components and make sure don't cause the bottleneck in the system again". Hard performance
rules: the page stack renders lazily (only pages in view, virtualised) at thumbnail resolution; full size
only in the export payload, capped at ~200 dpi for the page (PR #2126 QUOTE-PERF-HOTFIX brings the cap; merge
origin/main after it lands and reuse it); no request per page on open (one list call, one preview call per
visible page window); no refetch loops; export stays one render at a time (the `catalogue_render` queue).
Test: a 30-page sheet mounts at most the visible pages.

## Contract

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend`.

### Data: table `projects.quotation_spec_sheets` (model `ProjectQuotationSpecSheet`, `BE/models/projects.py`)

`CompanyScopedMixin`, `__audit_track__ = True`. Columns: `id` UUID pk; `document_id` FK
`projects.quotation_documents.id` CASCADE, not null; `issue_id` FK `projects.quotation_issues.id` CASCADE,
NULL = built from the draft; `based_on_issue_no` int null (newest issue_no when a draft sheet was made);
`sheet_no` int not null; `cover_template_id`, `page_template_id`, `single_page_template_id` (FK tag templates,
SET NULL, single nullable); `cover_version_id`, `page_version_id`, `single_version_id` (FK tag template
versions, SET NULL); `items` JSONB not null (snapshot, below); `rows` JSONB not null default `[]` (#2103 row
shape `{key, area, comment, marker, hidden, accessories}`); `page_edits` JSONB not null default `{}`
(`{page_key: {"layers": [...]}}`, `page_key` = item key or `cover`); `items_taken_at` timestamp not null;
`page_count` int not null; `last_exported_at` timestamp null; `created_by`, `updated_by` (users FK SET NULL);
`created_at`, `updated_at`. Unique `(document_id, sheet_no)`; index `document_id`.

Item snapshot (one per item key, quotation order; what `pages()` needs, so pages never read live lines):
`{key, line_id, product_id, code, description, brand, image_attachment_id, drawing_attachment_id,
section, unit_price (float|null), set_parts: [{product_id, product_code, description}]}`.
Issue source: the issue's frozen scope pairs (`_issue_lines`). Draft source: each scope
(`qdocs.list_scopes`) at `project_quotation_service.current_version`, same section rule.

Migration `ssv2_0001_spec_sheets` (down_revision = main's head at build time, re-parent before PR): create
the table; backfill: each `quotation_documents` row whose `spec_sheet` has `cover_template_id` and
`page_template_id` and that has an issue gets `SS1` on its saved `issue_id` (else newest issue), items
snapshot from that issue, its rows, the templates' current `published_version_id`. Python in the
migration may call a pure function shared with the service (snapshot builder) only if it imports nothing
model-level that later migrations change; otherwise inline SQL. Idempotent (skip documents that already
have a sheet). Downgrade drops the table. The old column stays (not read any more by the tab).

### Service `BE/services/project_spec_sheet_service.py` (refactor in place, keep the #2103 page rules)

- `snapshot_items(db, document, issue_or_none) -> list[dict]`; `pages(db, sheet) -> list[dict]` builds pages
  from `sheet.items` + `sheet.rows` (same absorbed / order / area default / hidden rules as today).
- `sources(db, document)`: `[{value: "draft", label: "Current draft", hint}]` first when the document has no
  issue (hint "not issued yet") or any scope's current version differs from the newest issue's pair for
  that scope (or the scope is not in it) (hint "changed after R2 · not issued"); then every issue newest
  first `{value: issue.id, label: quotation_no(document_no, issue_no, revision_label), hint: "issued 03 Nov 2026"}`.
- `create_sheet(db, document, *, source, cover_template_id, page_template_id, single_page_template_id, user_id)`:
  template checks as `_templates_for` (published, family, same size; 422 codes kept); `source` "draft" or an
  issue id of THIS document (else 422 `spec_sheet_issue_invalid`); 422 `spec_sheet_no_lines` when the
  snapshot has no item; `sheet_no = max+1`; rows `[]` (clean start, Q4); pins version ids; sets
  `page_count`.
- `update_sheet(db, sheet, payload)`: `rows` merge exactly as #2103 `save_settings` (+ `_check_rows`);
  `use_latest_templates: true` re-pins the three version ids to the templates' current published versions
  (422 if a template is gone / unpublished / size differs); recompute `page_count`; stamp `updated_*`.
- `save_page_edit(db, sheet, key, layers)` (key must be `cover` or a page key of the sheet, else 404;
  layers list <= 300 entries) / `reset_page_edit(db, sheet, key)`.
- `build_print_payload(db, sheet, *, keys=None, full=False)`: as today but from the sheet: templates =
  pinned VERSION docs (not `published_version`), a page with an edit uses its edit's layers; `keys` limits
  the sheets (window); `full=False` signs thumbnails (`preview_urls(full=False)`), `full=True` for export
  only (cap from #2126 when it lands). Preview includes hidden pages (flagged in a `hidden` key list) so the
  reader can grey them; export prints visible only.
- `request_export(db, sheet, user_id)`: download `source_entity_type="quotation_spec_sheet"`,
  `source_entity_id=sheet.id`, filename `spec-sheet-<quotation no or "PRJQ-2026-0027-draft">-SS<n>.pdf`,
  queue `catalogue_render`; stamps `last_exported_at`. `print_payload_for_download` /
  `page_size_for_download` resolve the sheet (legacy `quotation_issue` sources answer 404), company pinned
  as today, `full=True`.
- Deferred actions: register `quotation_spec_sheet.delete` (hard delete) and
  `quotation_spec_sheet.reset_page` (payload `{page_key}`) in `BE/services/record_actions.py` +
  `BE/api/v1/system/pending_actions.py`, following `quotation_document.delete` (UUID entity, visibility +
  edit-right check at park AND at commit).

### Routes `BE/api/v1/projects/spec_sheet.py` (replace the #2103 four)

`S = /projects/{project_id}/quotation-documents/{document_id}/spec-sheets`
- `GET S` (READ) -> `{items: [row], sources, templates: {cover, page}, defaults: {source, cover_template_id,
  page_template_id, single_page_template_id}, create_disabled_reason: str|null}`. row: `{id, sheet_no,
  label: "SS2", source_label, source_hint, is_draft, cover_name, page_name, single_name, page_count,
  edited_count, created_by_name, created_at, updated_at, last_exported_at, newer_templates}`. Defaults:
  first source; templates from this user's newest sheet anywhere (company scope), else null.
- `POST S` (EDIT + write) body `{source, cover_template_id, page_template_id, single_page_template_id?}` -> 201 detail.
- `GET S/{sheet_id}` (READ) -> detail `{id, sheet_no, label, source_label, source_hint, is_draft,
  templates: {cover:{id,name,version_no}, page:..., single:...|null}, newer_templates, page_size:{width_mm,height_mm},
  pages: [{key, number|null, code, name, brand, area, area_default, comment, marker, hidden, picked,
  accessories, edited, template: "cover"|"page"|"single"}] (cover first), prev_id, next_id,
  can_edit}`. No per-page images here.
- `PATCH S/{sheet_id}` (EDIT + write) `{rows?, use_latest_templates?}` -> detail.
- `GET S/{sheet_id}/preview?keys=k1,k2,...` (READ; <= 12 keys, unknown key 422) -> print payload for those
  pages, thumbnails only, + `hidden: [keys]`, `page_size`.
- `GET S/{sheet_id}/pages/{key}/design` (EDIT) -> `{layers, bound: <that page's resolved row>, images, assets,
  fonts, width_mm, height_mm, template_name}` for the designer (thumbnail images).
- `PUT S/{sheet_id}/pages/{key}/edit` (EDIT + write) `{layers}` -> detail.
- `POST S/{sheet_id}/export` (READ, as #2103) -> download.
- Every route: project -> document -> sheet ownership checked; a sheet of another document is 404.
- `tests/portal_p2_allowed_routes.txt`: replace the four old lines with the new ones.

### Frontend

- `FE/app/(protected)/project-sales/_shared/services/specSheetService.ts` + `hooks/useSpecSheet.ts`: rewritten
  for the contract; queries with `refetchOnWindowFocus: false`; mutations invalidate the list + that sheet.
- Tab `.../[documentId]/(view)/spec-sheet/page.tsx` -> `QuotationSpecSheetsList` (`PanelDataGrid`, fixed layout,
  resizable, sized columns, `rowHref` to the sheet, row menu View / Export PDF / Delete with
  `DeferredActionButton` + `useDeferredAction`), header CTA "Create spec sheet" (disabled with
  `create_disabled_reason` as title), empty state.
- `CreateSpecSheetDialog` (`FormDialogScaffold`, `SearchableSelect` x4, Single clearable) -> on success
  `router.push` to the sheet.
- Route `.../[documentId]/spec-sheet/[sheetId]/page.tsx` -> `SpecSheetReader`: header (label, source, template
  versions, "newer template published" badge + Use latest templates, RecordNavigation prev/next, Export PDF,
  Delete in the menu); toolbar (page N of M, zoom out/in, fit width using `pdf-viewer/zoom.ts` helpers);
  rail (labels; drag via `components/ui/sortable.tsx`, pages direct children); stack: one fixed-aspect
  placeholder per page sized from `page_size`, an IntersectionObserver (rootMargin one screen) decides the
  visible window; the window's keys are fetched with ONE preview call (query key = sorted keys, chunked
  to 12) and only pages in the window mount `ScaledSheet` / `TagSheetRenderer`; pages outside unmount.
  #2103's on-page AREA / COMMENT / marker typing, Leave out / Put back, Add accessory move into each page's
  bar (PATCH rows). Edited badge + Reset to template (deferred `quotation_spec_sheet.reset_page`).
- Edit page: route `.../spec-sheet/[sheetId]/pages/[key]/edit` hosting `TagCanvasEditor` (`specSheet`,
  `boundData` from the design call, `hideSaveBar`, own Save page / Cancel / Open template), banner text from
  the mock.
- Delete the old `QuotationSpecSheetTab*` component + tests once replaced.

## Red test list (tester writes these first)

BE `tests/test_project_spec_sheets_v2.py` (blank_session; seed like `test_project_spec_sheet.py`):
1 create from an issue snapshots items, pins versions, sheet_no 1 then 2; rows start empty (Q4).
2 create from draft before any issue; later line edit does not change the sheet's pages; source label "Draft".
3 sources: draft first only when lines changed after the newest issue; proposal labels `-A`/`-B`.
4 create refusals: unpublished / wrong family / size mismatch / issue of another document / no lines.
5 pages() from the snapshot keep #2103 rules (set parts, picked accessory absorbed, hidden, area default).
6 PATCH rows merge + `_check_rows` refusals; edits to SS2 leave SS1 unchanged.
7 page edit: payload for that page uses the edit's layers, other pages and the template unchanged; reset.
8 re-published template: sheet keeps old version doc; `newer_templates` true; use_latest re-pins and keeps edits.
9 preview `keys` window returns only those sheets, signs thumbnails (`full=False`), > 12 keys 422; export payload full and visible only.
10 export: download source = sheet, filename, `last_exported_at`; print payload route answers it, company pinned, fail closed without company; legacy source 404.
11 deferred delete and reset_page registered: park needs edit right; commit hard-deletes; sheet of another document 404 on every route.
12 rights: read-only user lists / views / exports, gets 403 on create / patch / page edit.
13 migration backfill: a set-up document becomes SS1; a document without templates or issue gets none; rerun no duplicate.
14 list `defaults` take the user's newest sheet templates; `create_disabled_reason` when no lines.

FE (vitest):
15 `SpecSheetReader` with a 30-page sheet in jsdom with a mocked IntersectionObserver reporting pages 1-3
visible: at most the visible pages (+ the window margin, assert <= 4) mount `TagSheetRenderer`; exactly ONE
preview request for that window; scrolling to 10-12 issues one more request and unmounts 1-3.
16 list renders rows / empty state / disabled CTA reason; Delete starts the deferred countdown (no confirm).
17 create dialog: sources with draft first, Single clearable, submit body, navigates to the sheet.
18 queries have `refetchOnWindowFocus: false` (hook test).
