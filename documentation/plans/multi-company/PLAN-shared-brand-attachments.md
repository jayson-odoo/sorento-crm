# PLAN: Shared brand attachments and folders across companies + product-code prefix tier

**Status:** Grilled 2026-08-31 (rounds 1-4, R1-R21), lavish-reviewed + apple-design pass (R22-R27) the same day, captain said proceed. Issues: S1 #435 (PR A), S2 #436 (FE mock), S3 #437 (BE core), S4 #438 (BE linkages + certs), S5 #439 (review + browser). S1 = PR #440 (review round 1 in progress: opt-in gate B1). S2 = draft PR #442 (FE mock, vitest 8990 green; agent-browser pass BLOCKED: :3100 held by the apple-preview lane's dev server, pid 51030). S3 coder spawned on `feat/shared-brand-S3-be-core`, stacked on S2 - tests landed (`773612a18`). S4 coder on `feat/shared-brand-S4-linkages-certs`, stacked on S3: `company` filter (AC-E1), linked-entity widening (AC-G1-G4), certificate follow (AC-H1-H6) DONE, migration 449 extended with a 4th piece (`certificates.company_id` NOT NULL drop/restore, missed at grill time - AC-H7 and this plan's migration bullet corrected in the same change), 26 new tests green (19 own + 7 fixed in the merged S3 test file).
**UAC:** `shared-brand-attachments-acceptance-criteria.md` (alongside; journey at its top).
**Domain:** multi-company / resources / certificates. Touches the ONE product-code resolver.
**Lane:** this session's port pair is :3100/:8100 (:3090 belongs to the spec lane).

## 1. Problem, measured on the prod-copy DB (31 Aug 2026)

Two companies, Sorento (`00000000-0000-0000-0000-000000000001`) and Mocha
(`5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f`). Products are per-company ROWS: 11,390
product codes exist as a twin pair (one row per company), 283 exist in one company only
(`uq_products_company_product_code`).

Certificates, product photos and technical specifications are brand-level documents:
the same file is true for both companies. Today they are owned by one company:

| | Sorento | Mocha | NULL (shared) |
|---|---|---|---|
| Product Photos | 2,674 | 0 | 13 |
| Technical Specifications | 986 | 0 | 0 |
| Certification (`is_certificate`) | 16 | 0 | 0 |
| Packing List | 43 | 0 | 3 |
| attachments, any type | ~4,250 | 1 | ~150 |
| attachment_directories | 636 | 0 | 0 (column is NOT NULL) |

So Mocha's 11,390 twin products carry zero photos, specs or certificates, and the only
way to change that today is to upload and link every file a second time under Mocha and
maintain both copies.

Second defect, same feature: n8n reads a certificate and returns
`"SRTBV - BRASS BALL VALVE"` as a product code. The resolver
(`app/services/product_code_resolution.py`, tiers exact / product set / `+` split /
substring) normalises it to `srtbv-brassballvalve`, no tier matches, the code lands in
`skipped_product_codes`. The cert names a code FAMILY: `SRTBV110-DIY` .. `SRTBV180-DIY`,
`SRTBVB8013` (9 per company, 18 rows).

## 2. What already exists (do not rebuild)

- `attachments.company_id` is nullable and the model declares `__company_shared__ = True`.
  Under any company scope the predicate is `company_id IS NULL OR company_id IN (scope)`
  (`app/services/company_scope.py::build_company_predicate`, UAC multi-company AC-H5).
  **NULL company = visible to every company.** ~150 rows use it today (form attachments).
- FE already renders a NULL company as `Shared`
  (`resource-management/attachments/types/attachment.types.ts::attachmentCompanyLabel`).
- Upload stamping: `resources_service.py::_single_active_company` + `_inherit_company_from_folder`
  (`~471-530`). The latter ALSO re-stamps a NULL-company file when it is MOVED into a folder.
  That move-time re-stamp is removed by this plan (R10).
- Bulk endpoint precedent: `POST /resource-management/attachments/bulk-attachment-type`
  (`BulkAttachmentTypeRequest {attachment_ids, attachment_type_id}` ->
  `BulkAttachmentTypeResponse {updated_attachments, attachment_type_id}`), served by
  `AttachmentService.bulk_set_attachment_type` (`resources_service.py:1678`), guard
  `get_current_user`. Same endpoint serves the popup's single-row Edit and the bulk action.
- Drive page (`/resource-management/attachment-directories`, "All files"): selection strip
  `Action` dropdown from `components/driveBulkActions.ts::buildDriveBulkActions`; row
  context menu `components/DriveRowActions.tsx` (files: `Open / Preview / Download / Reveal
  in folder / Rename / Move to... / Resubmit to n8n / Move to trash`; folders: `Rename /
  Move to... / ...`). Neither list shows a company column today.
- Files listing (`/resource-management/attachments`, `AttachmentBrowser.tsx`): own
  `bulkActions` (`Attachment type (n)`, `Resubmit selected (n)`, `Delete selected (n)`).
- `AttachmentType` is a GLOBAL table (no company scope), edited on the Attachment Types
  page; it already carries `is_certificate`.
- n8n callback: `POST /external/product-attachments/link-products` ->
  `_link_attachment_to_products_bulk` (`app/api/v1/external/product_attachments.py`), which
  pins the session scope to the attachment's company via `scope_to_attachment_company`
  and leaves the scope at `None` (all companies) when the attachment has no company.
  Under `None` the resolver returns BOTH twins already.
- Certificates: `certificate_service.py:970` already stamps projected `product_attachments`
  rows from `certificate.company_id` explicitly. Same pattern, reused per product here.
- Expiry alerts are automation rules (`automation_service.py`, `_stamp_expiry_batch`); the
  first rule to sweep a certificate stamps `expiry_notified_at`, later sweeps skip it.
- Resubmit: `POST /attachments/{id}/resubmit` (per row) and bulk resubmit in both toolbars.
  Unchanged.

## 3. Rulings (captain, 31 Aug 2026, grill rounds 1-4)

- **R1** No backfill migration. Sharing existing rows is a user action in the UI, applied
  to what the user filters and selects.
- **R2** Nothing is deleted first. The files live in Sorento; the user shares them from
  Sorento.
- **R3** A single-company attachment keeps today's popup behaviour: linked products are the
  active company's. Only a SHARED attachment shows linkages across companies.
- **R4** The action lives in the drive page's `Action` dropdown AND the row context menu
  (files and folders), in the Files listing toolbar for parity, and as an inline `Edit` on
  the popup's Company field. One dialog, one endpoint.
- **R5** Certificates follow their attachment's company. Shared attachment = shared
  certificate = one expiry alert (whichever company's automation sweeps first).
- **R6** Both: the deterministic twin linker AND the n8n resubmit. The linker runs on EVERY
  company change, synchronously, inside the same request: one company -> shared EXPANDS
  links to the twins; shared -> one company SHRINKS to that company; A -> B MOVES. The LLM
  / n8n run is only ever triggered by the user's Resubmit.
- **R7** `SRTBV` is fixed in the ONE resolver as a last-resort tier; never in the n8n
  prompt, never by splitting every whitespace token. Constants hardcoded; `via` surfaced.
- **R8** No M2M `attachment_companies`. Trigger to revisit: a third company that must not
  see some brand documents. Until then NULL = shared with all.
- **R9** No on-screen explanation of what Shared means (visual-fatigue rule).
- **R10** Company is decided ONCE at upload (by the attachment type, R11) and afterwards
  only by the `Set company…` action. A move never re-stamps a company.
- **R11** `attachment_types.is_shared`: an upload of a type flagged shared is written with
  `company_id = NULL`. Flipping the flag does not touch existing rows (R1).
- **R12** No type is rejected by the endpoint. The user filters by type and the grace
  window (R22) is the safety net. (Packing lists stay company documents by practice, not by rule.)
- **R13** No new permission: `bulk-company` uses the same guard as `PUT /attachments/{id}`.
- **R14** `Company` column on the drive list (files and folders), narrow, at the right.
- **R15** An out-of-scope twin in the popup is plain text with a company badge; no
  company switch from inside a popup.
- **R16** A move or share that leaves a file with no product twin proceeds; the toast
  counts say what happened.
- **R17** Folders are shareable the same way: `attachment_directories.company_id` becomes
  nullable, the model gets `__company_shared__ = True`, and folders get `Set company…`.
  No dedicated create-shared-folder UI: create, then `Set company… -> Shared`.
- **R18** Folder `Set company…` is RECURSIVE downward: subfolders and files inside take the
  same company, and the twin linker runs for every file.
- **R19** INVARIANT: every ancestor folder of a shared folder or shared file is shared.
  Sharing pulls the path up (folders only, sibling files untouched); the system does it on
  share, on upload of an `is_shared` type into an owned folder, and on moving a shared item
  into an owned folder. Owning pushes only down (R18); an owned folder under a shared parent
  is allowed, and un-sharing a file leaves its folder shared.
- **R20** A new folder inherits its parent's company (shared under shared); at root it takes
  the active company.
- **R21** Counts: the server response carries `updated_directories`, `updated_attachments`, `links_added`, `links_removed`, `certificates_updated` (asserted in tests); the UI toasts follow R22.
- **R22** (apple-design pass, Agency) Set company is reversible, so it is NOT a confirmation. The dialog is only the picker; `Apply` starts a DEFERRED action through the shipped grace-window engine (Apple-alignment S6): registry keys `attachment.set_company` (entity `attachment`) and `attachment_directory.set_company` (entity `attachment_directory`), `window="reversible"` (5 s, `system_settings.deferred_action_seconds`), FE via `hooks/useDeferredBulkAction.tsx` (one target per selected file / folder, payload `{company_id}`), pending toast = `Setting company for 3 folders, 12 files` + Cancel, commit toast = `Company set: 3 folders, 12 files`; Cancel inside the window changes nothing. Link counts are visible in the popup after commit.
- **R23** (Familiarity) Verb labels: `Set company…` in the row context menu (ellipsis = a dialog follows), `Set company` in the Action dropdown, beside `Set attachment type`.
- **R24** (D15, one action set per entity) The action is added to the two existing definitions only (`DriveRowActions.tsx`, `AttachmentBrowser.tsx` bulk arrays) and the popup `Edit` reuses the same dialog; no new action surface.
- **R25** (Craft, one status language) Company column and popup badge use the shipped `Badge` primitive, tinted (`appearance="light"`), text = company name or `Shared`, no status dot; `truncate` + `title`.
- **R26** (Status during work) The twin linker is SET-BASED: one `INSERT … SELECT` and one `DELETE` per call, never a per-file loop, so a whole folder (2,674 files) commits inside one execute. Trigger for moving it to the worker: a measured execute over ~10 s.
- **R27** (Same look = same behaviour) The out-of-scope twin row in the popup is muted plain text, no underline, no hover; the badge sits beside it.

## 4. Design

### S1. Resolver tier 5: `VIA_PREFIX` (head token, prefix match)

`app/services/product_code_resolution.py`, appended AFTER `_substring` in the `or` chain, so
every existing match is untouched.

Measured guard rails (products table, 23,063 rows):
- 318 codes contain a space (`32MM TAIL PIECE COUPLING`, `SRTWB1514-WALL HUNG`,
  `CB 90024E2-2B`), 7 contain ` - `. They match at tier 1 today and must keep doing so; the
  new tier only runs when tiers 1-4 all miss.
- Prefix hits: `SRTBV` 18, `BRASS`/`BALL`/`VALVE`/`SPAN`/`WCM`/`DIY`/`TAIL` 0, `BOM` 10, `SRT`
  **9,655**. Hence head-only, prefix-only, min length 4, fan-out cap.

Rule:
1. `head` = text left of the first ` - ` (spaces on both sides) if present; else the first
   whitespace-delimited token. Skip the tier when `head` normalises to the whole code.
2. `head` qualifies when `len(normalize(head)) >= 4` (`PREFIX_MIN_HEAD = 4`).
3. Query: `lower(replace(product_code, ' ', '')) LIKE '<normalized head>%'`, ordered by
   `product_code`.
4. `PREFIX_MAX_FANOUT = 200` DISTINCT normalised product codes (not rows: twin rows exist
   in both companies, so under the all-companies scope 200 rows would be ~100 codes); more
   = the code goes to `unmatched`, nothing linked. `%` and `_` in the head are escaped.
   Ordering ends with `Product.id`.
5. `CodeMatch.via = "prefix"` (`VIA_PREFIX`), `requested_code` = the original string.
6. `ProductAttachmentBulkLinkItem` gains `via: str` so the Integration tab shows how each
   link was reached.
7. **Opt-in (review finding B1 on PR #440).** The resolver has four callers. The tier runs
   only when `resolve_codes_to_products(db, codes, allow_prefix=True)`, and only the
   attachment link path passes it (`_link_attachment_to_products_bulk` and the certificate
   adapter). The single-code `POST /external/product-attachments`, the packing-list ingest
   (would write inbound-shipment lines at full quantity per family member) and promotions
   (pricing links) stay on tiers 1-4; each has a test proving a family head still lands in
   its skip / miss path. Trigger to widen: a real packing list or flyer that names a family.

### S2. `POST /resource-management/attachments/bulk-company` + the twin linker

**Two entry points, one service.** The UI never calls the endpoint directly (R22): it starts
deferred actions, and the engine calls the service at commit. The endpoint exists for the
popup single-row Edit fallback, for tests, and for n8n-style callers.

- Registry (`app/services/record_actions.py`, **not** `form_actions.py` - S3 coder correction:
  `form_actions.py` is the form-SLA undo registry (PR/SI/CX/ticket pairs with `capture`/`invert`
  snapshots); `record_actions.py` is where `product.delete`, `order.set_status` etc already live,
  the exact "wrap an existing service method behind a deferred action, permission checked at
  park time" shape this needs. Same underlying `FormAction`/`register` machinery either way, just
  the file `product.delete` is precedent for.): `attachment.set_company`
  (`entity_types=("attachment",)`) and `attachment_directory.set_company`
  (`entity_types=("attachment_directory",)`), both `window=WINDOW_REVERSIBLE`,
  `execute=lambda db, payload: AttachmentCompanyService(db).apply(...)`
  with `payload = {"company_id": str | None}`; the entity id is the target. A bulk selection
  is N pending actions (one per file / folder), exactly how `product.delete` bulk works
  (`ProductsList.tsx` -> `useDeferredBulkAction`). `permission=OWN_RECORD` (record_actions.py's
  "just signed in" sentinel), matching R13's "same guard as `PUT /attachments/{id}`" - the route
  has no permission slug of its own; `AttachmentCompanyService` separately checks the target
  company against the actor's grants (AC-B6).
- **Request** `BulkCompanyRequest { attachment_ids: list[str] = [], directory_ids: list[str] = [], company_id: str | None }`
  (at least one id overall; `None` = shared). **Response**
  `BulkCompanyResponse { updated_directories: int, updated_attachments: int, company_id: str | None, links_added: int, links_removed: int, certificates_updated: int }`.
  The execute path returns the same counts.

Guard: the same dependency as `PUT /attachments/{id}` (R13); the deferred engine's RBAC check
uses the same slug. `company_id`, when not None,
must be in the caller's grants (`company_scope_resolver._user_grant_ids`) else 403. Every id
must resolve under the caller's scope (a foreign id is a 404 for the whole call). One
transaction, all-or-nothing, like `bulk-attachment-type`.

Resolution order inside the request (`app/services/attachment_company_service.py`, new):

1. **Expand folders downward (R18):** every selected folder plus all descendants (folders
   and files, `is_deleted = false`), read UNSCOPED (the service sets the session scope to
   `None` in a `try/finally` that restores the caller's scope; ORM only, never `text()`).
2. **Pull ancestors up when sharing (R19):** when `company_id is None`, add every ancestor
   folder of every selected folder and of every selected file's folder. Folders only.
3. Set `company_id` on every collected folder and file.
4. **Twin linker** over the whole collected file set, SET-BASED (R26,
   `sync_product_links_for_company(db, attachment_ids, target)`):
   - `targets` = all company ids when shared, else `{company_id}`;
   - one `INSERT INTO product_attachments (...) SELECT ...` from the existing link rows
     joined to `products` twice (source product -> same `product_code` in a target company),
     anti-joined against existing `(product_id, attachment_id)`, with `company_id` taken from
     the twin product (explicit, so the auto-stamp never runs), copying `access_levels`,
     `is_primary`, `sort_order`, `linked_via_set_id` from the source row; written through the
     ORM `insert(...).from_select(...)` so the scope listener and audit still see it, never
     `text()`;
   - one `DELETE` of link rows whose product `company_id` is outside `targets`;
   - `AttachmentFieldLinkService.apply_template_to_row` for each inserted row (returned via
     `RETURNING`), as the n8n path does;
   - a missing twin (283 single-company codes) adds nothing, no error (R16).
5. **Certificate follow (S5)** for every collected file that is a filed certificate revision.
6. One commit; response counts.

**Latent bug fixed in the same slice:** `_link_attachment_to_products_bulk` sets
`company_id = product.company_id` on every `ProductAttachmentCreate` it writes. Today, under
the API-key `None` scope, a shared attachment's Mocha link would auto-stamp
`DEFAULT_COMPANY_ID` (Sorento) and be invisible to Mocha (child-row split gotcha,
`project_company_scope_child_rows_split`). 0 / 3,446 rows are mismatched today only because
no product attachment is NULL-company yet. `ProductAttachmentCreate` gains optional
`company_id`; `create_product_attachment` writes it when present.

### S3. Upload, move, create: the company rules (R10, R11, R19, R20)

- Migration: `attachment_types.is_shared boolean not null default false`;
  `attachment_directories.company_id` DROP NOT NULL and drop its server default;
  `AttachmentDirectory.__company_shared__ = True`.
- `create_attachment`: type `is_shared` -> `company_id = NULL`, then pull the destination
  folder's ancestor chain to shared (R19); otherwise today's rule (single active company).
- `_inherit_company_from_folder` is called from the CREATE path only; the move path no
  longer re-stamps (R10). Moving a shared file or folder into an owned folder pulls that
  folder's chain to shared (R19).
- Folder create: `company_id = parent.company_id` (NULL under a shared parent); at root the
  single active company (R20).
- Attachment Types page: `Shared` checkbox next to the existing certificate flag.
- Drive tree: a shared folder appears in both companies at its real position (its ancestors
  are shared by R19, so the path always resolves).

### S4. Front end

**Drive page** (`attachment-directories`):
- `driveBulkActions.ts`: `{ key: 'bulk-company', label: 'Set company' }` between
  `Set attachment type` and `Resubmit selected`, outside trash, enabled for any mix of files
  and folders in the selection (R23, R24).
- `DriveRowActions.tsx`: `Set company…` after `Move to...` for files AND folders (R23).
- `Company` column (files and folders): `Badge appearance="light"` reading `Sorento` /
  `Mocha` / `Shared`, narrow, rightmost, explicit `size` (R14, R25).
- Company filter in the filter popover: `SearchableSelect`, `clearable`, options = granted
  companies + `Shared`; sent as `company=<id>` or `company=shared` on `GET /attachments/drive`
  (applies to folders and files in the stream).
- `SetCompanyDialog.tsx` (shared by both pages, under `resource-management/attachments/components/`):
  one required `SearchableSelect` (granted companies + `Shared`, focus on open, Enter
  applies, Escape closes), the selection count (`3 folders, 12 files`), `Apply` / `Cancel`.
  `Apply` calls `useDeferredBulkAction({ actionKey, entityType, invalidateKeys }).run(targets)`
  (files -> `attachment.set_company`, folders -> `attachment_directory.set_company`) and
  closes; the pending toast with Cancel and the commit toast come from the hook (R22).
  Error = extracted message.

**Files listing** (`AttachmentBrowser.tsx`): `Set company (n)` bulk action next to
`Attachment type (n)`; same dialog; same `company` filter on `GET /attachments`.

**Detail popup** (`AttachmentDetail.tsx`): `Company` value gets `Edit` (like Attachment
Type), opening the dialog with one id. Directory breadcrumb resolves in both companies
because of R19.

### S5. Linkages for a shared attachment (popup Products / Certificates tabs)

`resources_service.py` linked-entity builder (`~1372`): when `attachment.company_id is None`,
run the product and certificate link queries under scope
`frozenset(_user_grant_ids(current user))` instead of the request's single active company.
A user with one grant sees exactly what they see today.

`LinkedEntityRef` gains `company_id`, `company_name`, `in_scope` (true when the row's
company is the active company or the row has no company); declared on `AttachmentResponse`
and asserted in a test (undeclared fields are dropped silently).

FE `LinkedEntityList`: `Badge appearance="light"` on every row of a shared attachment (text =
the company name, nothing else, R25); `in_scope = false` rows render the name as muted plain
text, no `href`, no underline, no hover, no UUID (R15, R27). Single-company attachments render
exactly as today (R3).

### S6. Certificates follow the attachment (R5)

- `Certificate.__company_shared__ = True`; `company_id` stays nullable at ORM level (already).
- `uq_certificates_company_scheme_number` rebuilt on
  `coalesce(company_id, '00000000-0000-0000-0000-000000000000')` + the existing normalised
  expression, so two NULL certificates with one identity cannot coexist (Postgres treats
  NULLs as distinct in a plain unique index). Same migration as S3.
- `bulk-company` on a filed certificate revision (`ProductService._certificate_of_attachment`):
  `certificate.company_id = target`, coverage (`certificate_products`) rewritten with the same
  expand / shrink / move rule over product codes, then `CertificateService.reconcile_certificate`
  re-projects `product_attachments`, stamping each row from `product.company_id`
  (`certificate_service.py:970`; identical result for a single-company certificate).
- `upsert_from_extraction` (n8n path): the certificate takes `attachment.company_id` (NULL for
  a shared file) rather than the session's write company.
- Identity probe (`certificate_service.py:226`): under a company scope the shared predicate
  already includes NULL rows, so a resubmit finds the shared certificate.
- Register list: company column reads `Shared` for NULL; expiry: one alert (R5).

### S7. Resubmit (unchanged)

After sharing, the user selects the rows and `Resubmit selected`. n8n calls `link-products`;
scope stays `None`; the resolver returns both twins (plus S1's prefix tier); S2's explicit
stamp puts each link in its product's company; `already_linked` reports the rows the twin
linker already created.

## 5. Out of scope, named triggers

- M2M company grants per attachment (R8).
- Per-company expiry recipients for a shared certificate: an automation-recipient question;
  trigger = Mocha asks for its own recipients.
- A `Company` select on the folder create dialog (R17): trigger = users report the two-step
  create-then-share as friction.

## 6. Delivery

Two PRs so the tiny one ships first:

- **PR A - resolver prefix tier (S1).** Backend only, test-first.
  `app/services/product_code_resolution.py`, `app/schemas/external/attachments.py` (`via`),
  `tests/test_product_code_resolution.py`, the existing external product-attachment tests.
- **PR B - shared attachments and folders (S2-S7).** Phase 1 FE against mocks (dialog,
  column, filter, badge, popup Edit, Attachment Types checkbox, folder context item);
  Phase 2 BE test-first; Phase 3 `/code-review`; agent-browser evidence run from the sidebar.

### Files (PR B)

Backend
- alembic migration (one): `attachment_types.is_shared`; `attachment_directories.company_id`
  nullable, default dropped; certificate identity index rebuilt; `certificates.company_id`
  nullable too (S4 correction: migration 312 gave it NOT NULL, missed when this plan was
  written - `Certificate.__company_shared__` needs the same DROP NOT NULL / restore-with-
  stamp pair `attachment_directories.company_id` gets). `down_revision` = the main
  head at branch time, id <= 32 chars, `alembic heads` = one.
- `app/models/resources.py` (`AttachmentDirectory.__company_shared__`, `AttachmentType.is_shared`),
  `app/models/certificate.py` (`__company_shared__`).
- `app/schemas/resources.py`: `BulkCompanyRequest/Response`, `LinkedEntityRef` fields,
  `AttachmentTypeCreate/Update/Response.is_shared`, `company` filter.
- `app/api/v1/resources/attachments.py`: `bulk-company` route; `company` query on `/` and
  `/drive`. `app/api/v1/resources/attachment_types.py`: `is_shared`.
- `app/services/record_actions.py`: the two `set_company` registrations (R22; see the S3
  coder correction under S2 above - not `form_actions.py`).
- `app/services/attachment_company_service.py` (new): folder expansion, ancestor pull,
  twin linker, certificate follow, one transaction.
- `app/services/resources_service.py`: upload rule (`is_shared` -> NULL + ancestor pull),
  move path without re-stamp, move-time ancestor pull, folder create inherit, linked-entity
  widening, `company` filters.
- `app/api/v1/external/product_attachments.py`, `app/schemas/product.py`,
  `app/services/product_service.py`: explicit `company_id` on link rows.
- `app/services/certificate_service.py`: upsert company from attachment, per-product stamp,
  coverage rewrite hook.

Frontend
- `attachments/components/SetCompanyDialog.tsx` (+ test) on `hooks/useDeferredBulkAction.tsx`,
  `AttachmentBrowser.tsx`, `AttachmentDetail.tsx` (Company Edit, badges),
  `attachments/services/attachmentService.ts` (`bulkSetCompany` for the popup fallback + tests),
  `attachments/types/attachment.types.ts` (`LinkedEntityRef`, drive item company).
- `attachment-directories/components/driveBulkActions.ts`, `DriveRowActions.tsx`,
  `DriveListView.tsx` (Company column), `AttachmentDirectoriesView.tsx` (filter + dialog).
- Attachment Types page: `Shared` checkbox.

### Tests (Phase 2, Postgres only, `tests/_pg_fixture.py`, own seeded chain, `ZZT-` codes)

Listed per AC id in the UAC file; the tester asserts against those ids.
