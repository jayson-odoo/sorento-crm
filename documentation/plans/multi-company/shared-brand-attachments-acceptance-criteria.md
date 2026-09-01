# UAC: Shared brand attachments and folders across companies + product-code prefix tier

## Journey

**Actor:** a Sorento marketing / product-data staff member (granted both Sorento and Mocha,
Sorento active). **Arrives from:** the sidebar, Resource Management -> All files, the same
place they already upload photos, specs and certificates.

**What the system already knows:** every product code exists as a twin row in both
companies (11,390 of 11,673); every photo, spec and certificate is already linked to its
Sorento product; the attachment type says what kind of document it is; the folder tree
says where it lives.

1. They right-click the `Product Photo` folder -> `Set company… -> Shared -> Apply`.
   **The one decision.** Nothing else is asked: subfolders, files, the twins to link, the
   certificate to widen, the parent folders that must open in Mocha are all derived.
   (Cherry-picking works the same way: filter the list by type, tick rows,
   `Action -> Set company`.)
2. A toast counts down with Cancel (a slip is undone by one click); when it lapses the
   system marks the folder, its subfolders, its files and its parent folders shared, and
   links every file to the Mocha twin of every product it is linked to in Sorento; a filed
   certificate widens with it. The toast then says how many folders and files changed.
3. They open one file to check: `Company: Shared`; the Products tab lists the Sorento
   product (a link) and the Mocha product (a badge). Switching the active company to Mocha
   shows the same folder at the same place in the tree, and the same file; they do not
   have to.
4. Optionally they select the files and `Resubmit selected` so n8n re-reads them: family
   codes on a certificate (`SRTBV - ...`) now resolve to every `SRTBV...` product, in both
   companies.
5. From now on, an upload of a type flagged `Shared` on the Attachment Types page
   (Certification, Product Photos, Technical Specifications) is shared at upload; nothing
   to do later.
6. Later, a file or folder that should NOT have been shared: `Set company… -> Sorento`. Its
   Mocha links, and for a folder its contents, go with it.

**What they hold at the end:** one copy of each brand document, in one folder tree, visible
and linked in both companies, with links maintained for them on every later company change.

**Told automatically:** nobody. Sharing is a data-maintenance act, not an event; the
existing upload / link notifications from the n8n path stay as they are.

Plan: `PLAN-shared-brand-attachments.md`. Tags: `[BE]` pytest, `[FE]` vitest, `[E2E]`
agent-browser evidence run. Companies in every scenario: Sorento (S) and Mocha (M); the
tester seeds its own `ZZT-` twin products and `ZZT-` folders, never reads existing rows with
`LIMIT 1`, never lets a countdown lapse on the prod-copy DB.

## Group A - Resolver prefix tier (PR A)

- **AC-A1** `[BE]` Given products `ZZT-SRTBV110-DIY` .. `ZZT-SRTBV180-DIY` and `ZZT-SRTBVB8013` in
  S, When `resolve_codes_to_products(db, ["ZZT-SRTBV - BRASS BALL VALVE"])` runs under S scope,
  Then all 9 are returned with `via = "prefix"`, ordered by `product_code`, `unmatched` empty.
- **AC-A2** `[BE]` Given a product whose code contains a space (`ZZT-CB 90024E2-2B`), When that
  exact string is resolved, Then it matches at tier `exact`, never `prefix`.
- **AC-A3** `[BE]` Given `"ZZT - SOMETHING"` whose head normalises to fewer than 4 characters,
  Then the code is in `unmatched` and nothing is linked.
- **AC-A4** `[BE]` Given a head that prefix-matches more than 200 products, Then the code is in
  `unmatched` and no product is linked (no partial fan-out).
- **AC-A5** `[BE]` Every pre-existing resolver test passes unchanged (tiers 1-4 untouched).
- **AC-A6** `[BE]` Given `link-products` with `"ZZT-SRTBV - BRASS BALL VALVE"`, Then `linked`
  lists the 9 products each with `via = "prefix"`, `skipped_product_codes` and
  `already_linked` are empty, asserted on the HTTP JSON body through `response_model`.
- **AC-A7** `[BE]` Given the same family head sent to the packing-list ingest, the promotion
  ingest and the single-code `POST /external/product-attachments`, Then it lands in
  `skipped_product_codes` / `missing_codes` / 400 respectively: the tier is opt-in and only
  the attachment link path passes `allow_prefix=True`.
- **AC-A8** `[BE]` Given a family whose prefix matches 150 distinct codes as 300 twin rows
  under the all-companies scope, Then it resolves (the cap counts distinct codes).

## Group B - `bulk-company` on files: twin linker

- **AC-B1** `[BE]` Given an S file linked to `ZZT-A` (S row) and `ZZT-A` exists in M, When
  `bulk-company {attachment_ids:[f], company_id: null}`, Then `attachments.company_id` is NULL
  and a `product_attachments` row exists for the M twin with `company_id = M` and
  `access_levels`, `is_primary`, `sort_order` copied from the S row; `links_added = 1`.
- **AC-B2** `[BE]` Given a shared file linked to both twins, When `company_id: S`, Then the M
  link row is deleted, the S row stays; `links_removed = 1`.
- **AC-B3** `[BE]` Given an S file linked to `ZZT-A` (S), When `company_id: M` by a user granted
  both, Then the link points at the M twin only.
- **AC-B4** `[BE]` Given a linked code that exists in S only, When shared, Then nothing is added,
  no error; `links_added = 0`. When moved to M, the link is removed and the call succeeds.
- **AC-B5** `[BE]` Given an id belonging to a company outside the caller's scope, Then 404 and
  nothing is changed.
- **AC-B6** `[BE]` Given `company_id` names a company the caller is not granted, Then 403.
- **AC-B7** `[BE]` Given two ids, Then one transaction: a failure on the second leaves the
  first unchanged.
- **AC-B8** `[BE]` Given a shared file and an API-key `link-products` call, Then each created row
  carries `company_id = product.company_id` (M twin stamped M, not `DEFAULT_COMPANY_ID`).
- **AC-B9** `[BE]` Given the file's field-link template, When a twin row is added, Then
  `apply_template_to_row` ran for the twin.
- **AC-B10** `[BE]` The route is guarded by the same dependency as `PUT /attachments/{id}`;
  a user without it gets 403.
- **AC-B12** `[BE]` `attachment.set_company` and `attachment_directory.set_company` are
  registered with `window="reversible"`; creating a pending action, letting the window lapse
  (sweeper with a frozen clock) executes the service with the same result as AC-B1; cancelling
  inside the window changes nothing; a user without the route's permission is denied by the
  engine's RBAC check.
- **AC-B13** `[BE]` The linker issues one `INSERT … SELECT` and one `DELETE` for a call
  covering 500 seeded files (query count asserted), not one statement per file.
- **AC-B11** `[BE]` Given a Packing List file, Then it is accepted like any other (no type
  rejection).

## Group C - Folders: recursion and the ancestor invariant

- **AC-C1** `[BE]` Given `ZZT-root/ZZT-mid/ZZT-leaf` all S, with files in each, When
  `bulk-company {directory_ids:[mid], company_id: null}`, Then `mid`, `leaf`, every file under
  them, AND `root` are NULL; the twin linker ran for every file; `updated_directories = 3`.
- **AC-C2** `[BE]` Given the same tree with sibling file `x` directly in `root`, Then `x` keeps
  `company_id = S` (ancestor pull touches folders only).
- **AC-C3** `[BE]` Given a shared `mid` under shared `root`, When `mid` is set to S, Then `mid`,
  `leaf` and their files are S; `root` stays NULL (owning pushes only down).
- **AC-C4** `[BE]` Given a shared file in shared `leaf`, When the FILE is set to S, Then the file
  is S and `leaf` stays NULL.
- **AC-C5** `[BE]` Given a mixed selection (`directory_ids` + `attachment_ids`), Then both are
  applied in one transaction and counted separately.
- **AC-C6** `[BE]` Given a soft-deleted subfolder, Then it is not touched by the recursion.
- **AC-C7** `[BE]` Given `GET /attachments/drive` under M scope after AC-C1, Then `root`, `mid`,
  `leaf` and their files are returned at their real positions; `x` is not.

## Group D - Upload, move, create rules

- **AC-D1** `[BE]` Given attachment type `ZZT-Photos` with `is_shared = true`, When a file of
  that type is uploaded under S into owned folder `ZZT-own`, Then the file's `company_id` is
  NULL and `ZZT-own` and its ancestors become NULL.
- **AC-D2** `[BE]` Given a type with `is_shared = false`, When uploaded under S into a SHARED
  folder, Then the file is `S` (the type decides, the folder never does).
- **AC-D3** `[BE]` Given a NULL-company file moved (`PUT /{id}` with `directory_id`, and
  `bulk-move`) into an owned folder, Then the file stays NULL and the destination folder and
  its ancestors become NULL.
- **AC-D4** `[BE]` Given an S file moved into a shared folder, Then it stays S.
- **AC-D5** `[BE]` Given a folder created under a shared parent, Then its `company_id` is NULL;
  created at root under S, it is S.
- **AC-D6** `[BE]` Flipping `is_shared` on a type changes no existing attachment row.
- **AC-D7** `[BE]` `is_shared` round-trips through `attachment_types` create / update / list
  (declared on the response model, asserted on the JSON body).
- **AC-D8** `[FE]` The Attachment Types page shows a `Shared` checkbox beside the certificate
  flag, in the same position on create and edit.

## Group E - Filters, column and the listing

- **AC-E1** `[BE]` `GET /attachments?company=shared` under S scope returns only
  `company_id IS NULL` rows; `company=<S id>` only S rows; no param keeps today's
  `IS NULL OR IN (scope)` result. Same for `GET /attachments/drive`, folders included.
- **AC-E2** `[FE]` The drive filter popover and the Files filter popover carry a `Company`
  `SearchableSelect` (clearable): granted companies + `Shared`; selecting one sends the
  matching `company` param.
- **AC-E3** `[FE]` The drive list shows a `Company` column for files and folders rendering the
  shipped `Badge` (light appearance, no status dot) reading `Sorento` / `Mocha` / `Shared`,
  rightmost, explicit `size`, `truncate` + `title`.

## Group F - Actions in the UI

- **AC-F1** `[FE]` With 1+ rows selected on the drive page outside trash (files, folders or
  both), the `Action` dropdown contains `Set company` between `Set attachment type` and
  `Resubmit selected`; in trash it is absent.
- **AC-F2** `[FE]` A file row's context menu and a folder row's context menu both carry
  `Set company…` after `Move to...`, opening `SetCompanyDialog` for that one item.
- **AC-F3** `[FE]` The Files listing shows `Set company (n)` next to `Attachment type (n)`.
- **AC-F4** `[FE]` `SetCompanyDialog`: one required `SearchableSelect` (granted companies +
  `Shared`, focused on open; Enter applies; Escape closes), the selection count
  (`3 folders, 12 files`), `Apply` / `Cancel`. `Apply` starts one deferred action per selected
  file (`attachment.set_company`) and folder (`attachment_directory.set_company`) with payload
  `{company_id}` (null for Shared) through `useDeferredBulkAction`, then closes.
- **AC-F4b** `[FE]` The pending toast reads `Setting company for 3 folders, 12 files` with
  `Cancel`; Cancel inside the window leaves every row unchanged; on commit the toast reads
  `Company set: 3 folders, 12 files` and the drive / files / attachment queries are
  invalidated. No `AlertDialog` or confirm copy anywhere in the flow.
- **AC-F5** `[FE]` The detail popup's `Company` field has an `Edit` affordance opening the same
  dialog with that attachment's id; the value re-reads `Shared` after a null update (query
  invalidated).
- **AC-F6** `[FE]` No explanatory sentence about sharing appears anywhere in the UI (R9).

## Group G - Linkages on a shared attachment

- **AC-G1** `[BE]` Given a shared file linked to twins in S and M, and a user granted both with
  S active, `GET /attachments/{id}` returns both rows in `linked_products`, each with
  `company_id`, `company_name`, and `in_scope` true for S, false for M.
- **AC-G2** `[BE]` Same user with only an S grant: only the S row.
- **AC-G3** `[BE]` A single-company file returns exactly today's `linked_products`.
- **AC-G4** `[BE]` The three new fields survive `response_model` (asserted on the JSON body).
- **AC-G5** `[FE]` In the popup, a shared file's Products rows each show the `Badge` primitive
  with the company name; an `in_scope = false` row renders as muted plain text with no `href`,
  no underline, no hover state and no UUID; a single-company file renders with no badges. The
  Certificates tab follows the same rule.

## Group H - Certificates follow the attachment

- **AC-H1** `[BE]` Given a filed certificate whose current revision is an S file covering
  `ZZT-A` (S), When that file is set to Shared, Then `certificate.company_id` is NULL,
  `certificate_products` covers both twins, and the projected `product_attachments` rows are
  stamped per product; `certificates_updated = 1`.
- **AC-H2** `[BE]` Set back to S: coverage and projection shrink to the S twin.
- **AC-H3** `[BE]` A shared certificate appears once in the register under S scope and once
  under M scope.
- **AC-H4** `[BE]` A second NULL-company certificate with the same normalised identity is
  rejected by the rebuilt unique index.
- **AC-H5** `[BE]` `upsert_from_extraction` for a shared file under the API-key scope creates
  the certificate with `company_id` NULL and product resolution across both twins; for an S
  file it is S (unchanged).
- **AC-H6** `[BE]` The expiry sweep with a shared certificate near expiry produces one
  notification batch, not one per company.
- **AC-H7** `[BE]` Alembic: id <= 32 chars, `down_revision` = the main head (the migration
  was written as `449_shared_brand_attach` on `448_merge_s6b_ptag` and renumbered to
  `453_shared_brand_attach` on `452_transfer_days` when it was carried to main, so the
  assertion reads the current head, not the branch-time one), one head after upgrade; downgrade restores NOT NULL on `attachment_directories.company_id`
  (after stamping NULL rows with the incumbent company), drops `is_shared`, restores the old
  index. (S4 correction: `certificates.company_id` also had a NOT NULL from migration 312,
  missed when this AC was written - `Certificate.__company_shared__` needs it dropped in
  `upgrade()` the same way, and downgrade restores it the same way, stamping any NULL
  (shared) certificate to Sorento first.)

## Group I - End to end (agent-browser, sidebar navigation, one dev server)

- **AC-I1** `[E2E]` In S: Resource Management -> All files; right-click a `ZZT-` folder that
  holds two `ZZT-` photos -> `Set company… -> Shared -> Apply`. Pending toast with Cancel;
  let the window lapse (never cancel it by accident: the tester waits it out on `ZZT-` rows
  only); commit toast; the `Company` column reads `Shared` for the folder and its files.
- **AC-I1b** `[E2E]` Repeat on another `ZZT-` folder and press Cancel inside the window: the
  column still reads `Sorento`, the popup Products tab shows only the S twin.
- **AC-I2** `[E2E]` Open one file: Company reads `Shared`; the breadcrumb resolves; the
  Products tab lists the S twin (link) and the M twin (badge, plain text).
- **AC-I3** `[E2E]` Switch the active company to M (top-right switcher): the same folder is at
  the same place in the tree; open the file: the M twin is the in-scope link; the M twin's
  product page lists the file.
- **AC-I4** `[E2E]` Back in S, right-click the folder -> `Set company… -> Sorento -> Apply`,
  window lapses. In M the folder and files are gone; in S the popup shows only the S twin.
- **AC-I5** `[E2E]` Filter `Company = Shared` on the drive page narrows to shared rows; clear
  restores.
- **AC-I6** `[E2E]` Select shared files and `Resubmit selected`; after n8n returns, the popup
  shows no duplicate rows and the Integration tab payload shows `already_linked` covering the
  twin rows and `via` on each link.
- **AC-I7** `[E2E]` Dialog, filter popover, column and badges are usable and unclipped at
  375px and 1280px.
