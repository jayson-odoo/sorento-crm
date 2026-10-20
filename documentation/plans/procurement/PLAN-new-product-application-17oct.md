# PLAN - New product application (NEW-PRODUCT-APP)

Lane NEW-PRODUCT-APP, size L. Status: Build (v5 table form after the owner hand test FAIL on 20 Oct; v4 below). v4: reviewer
READY, security findings fixed, browser pass on the crew test copy done, owner hand test next. v1-v3 flow built and reviewed
earlier. Owner OKed card + mock v3 on 18 Oct (Q1 = portal too); crew PQ1 (b), PQ2 (a); owner then OKed mock v4 (18 Oct
12:14) with D1-D4 = yes and PQ1 = yes. v4 was rebuilt from the PR head because the cloud lane's v4 commits never reached
GitHub. Decisions taken in the build: Copy from the inquiry and image picks are staged on an unsaved draft and applied
after the first save; removing an image is staged until Save (no countdown needed); the Excel embeds the stored 320 px
thumbnail; NPA images are capped at 10 MB and 40 MP and checked by content.
Track: full (migration + new permissions). PR #1769, branch `claude/new-product-application-0u631d`.

Owner 15 Oct: stock inquiry about a new product code -> inquiry responded -> new product application ->
purchasing opens the product code after receiving the application.

- Behaviour card: `CARD-new-product-application-17oct.md` (the rules; this plan does not restate them).
- UAC: `new-product-application-acceptance-criteria.md`.
- Mock: `mockups/new-product-application-v4.html` (v1-v3 kept for the record).

## Design (simplest thing)

Copies the Sample Request (#1718) shape for the record and the quotation approval (#1698) for approve / lock /
revise. Paths: BE = `sorento_crm_backend/app/`, FE = `sorento_crm_frontend/`.

### Data (migration `npa_0001_new_product_apps`, parent = main's head at build time)

Public schema (procurement domain, like `stock_inquiries`), additive, idempotent (`IF NOT EXISTS`).

- `new_product_applications`: `id`, `company_id` NOT NULL, `application_no` (`NPA-000001`, unique per company),
  `status` VARCHAR(20) CHECK in (draft, submitted, approved, rejected, completed, cancelled), `applicant_id` -> users,
  `stock_inquiry_id` -> stock_inquiries ON DELETE SET NULL, `customer_id` -> customers SET NULL, `customer_name`,
  `project_name`, `needed_by` DATE, `remark`, `submitted_at`, `decided_at`, `decided_by` -> users,
  `reject_reason`, `cancelled_at`, `cancel_reason`, `completed_at`, `created_at`, `updated_at`.
- `new_product_application_lines`: `id`, `application_id` CASCADE, `line_no`, `proposed_code`, `description`,
  `further_description`, `category_id` -> product_categories, `base_uom_id` -> units_of_measure, `brand_id`,
  `item_type_id`, `supplier_id` -> suppliers, `supplier_item_code`, `cost_price` / `selling_price` NUMERIC(12,2),
  `expected_qty` NUMERIC(12,3) (all NULL-able), `remark`, `opened_product_id` -> products ON DELETE RESTRICT (product delete answers a 409 naming the application),
  `closed_reason`, `resolved_by` -> users, `resolved_at`. CHECK: not both opened and closed.
- Permissions `procurement.new_product_applications.view|create|approve|open_code` in
  `rbac/permission_registry.py` + migration grants: all four to superadmin/admin; `create` copied from holders of
  `procurement.stock_inquiries.edit` (the `sr_0001` pattern).

### BE

- `models/new_product_application.py` (`CompanyScopedMixin`, `__audit_track__`, number stamp copied from
  `models/sample_request.py` `next_request_no`).
- `services/new_product_application_service.py`: create / update draft, `assert_unlocked`, submit (incl. from
  Rejected), approve, reject, revise, cancel, link / close / undo line, auto-complete, list / detail / serialize,
  product search (reuses `sample_request_service.search_products`), recipients (`approver_user_ids` shape from
  `project_notify_service.py:70`, with the slug as a parameter), notify after commit.
- `api/v1/procurement/new_product_applications.py`, mounted in the procurement router; select endpoint for
  `item_types` (none exists today).
- Stock inquiry detail payload gains `new_product_applications: [{id, application_no, status, opened_codes}]`.
- `record_actions.py`: `new_product_application.delete` (WINDOW_DESTRUCTIVE, OWN_RECORD) +
  `pending_actions.py` pre-check, as `sample_request.delete`.
- `audit_logs.py`: entity type -> `procurement.new_product_applications.view`.

### FE

`app/(protected)/procurement-management/new-product-applications/` (page, new, `[id]`, `[id]/edit`, loading.tsx,
components List / Detail / Form / Lines, hooks, services, types), menu entry after Stock Inquiries,
`StockInquiryDetail.tsx` gear item + "New product applications" row.

## Test list (red first, by the tester before the coder)

pytest `tests/test_new_product_application.py` on the Postgres fixture: one test per AC-NPA-01..53 BE criterion,
plus: company isolation (404 / not listed / ORM None), lock guard on every write route, number never reissued after
delete, notifications fire after commit only and a raising sender does not undo the move.
vitest: form pre-fill from an inquiry (text only, no debtor id), no auto-pick in the link search, clearable number
fields send null, Submit / Approve / Reject / Revise buttons per viewer and status, inquiry row empty state.

Whole-tree guards to run locally before handoff (they only run in the full suite, see #1763):
`tests/test_company_scope.py` (`expected_owned` count), `tests/test_list_api_perms.py`, audit entity type tests,
FE `loading-inventory.test.tsx`, `data-grid.nested.inventory.test.ts`, `config/menu.config.test.ts`. Run the full
backend suite and the full vitest suite once before asking for the `ci` label.

## Data

Real examples: `crew-data-request` on PR #1769 (17 Oct). Rows stay out of the repo; the mock uses one masked case.

## API contract (as built, BE green on 2bd5343b)

Staff, base `/api/v1/procurement/new-product-applications` (module `procurement`):

| Method + path | Who | Body / query | Answer |
|---|---|---|---|
| GET `` | any of view/create/approve/open_code (403 otherwise) | `status` (comma list), `q`, `stock_inquiry_id`, `applicant_id`, `page`, `limit`, `sort` (application_no, status, created_at, submitted_at, needed_by, customer_name), `dir` | `{items: Summary[], total, page, limit}`; create-only callers see their own |
| POST `` | create | Write | 201 Detail (draft) |
| GET `/prefill?stock_inquiry_id=` | create | | Write-shaped body copied as text from the inquiry + `stock_inquiry_number` |
| GET `/products?q=` | open_code | | `[{id, product_code, product_name, brand_name, ...}]` (empty q = []) |
| GET `/item-types?q=` | any NPA slug | | `[{id, item_type_code, item_type_name}]` |
| GET `/{id}` | owner or view/approve/open_code | | Detail |
| PUT `/{id}` | create + owner | Write (lines replace all) | Detail; 422 `new_product_application_locked` when submitted/approved; 409 when completed/cancelled |
| POST `/{id}/submit` | owner | | Detail; 422 names "Line N: ..." |
| POST `/{id}/approve` | approve | | Detail; 409 unless submitted |
| POST `/{id}/reject` | approve | `{reason}` required | Detail |
| POST `/{id}/revise` | owner or approve | `{reason}` required | Detail (draft); 409 once a line is resolved |
| POST `/{id}/cancel` | owner | `{reason?}` | Detail; 409 once a line is resolved |
| POST `/{id}/lines/{lineId}/link` | open_code | `{product_id}` | Detail (auto Completed when every line is done) |
| POST `/{id}/lines/{lineId}/close` | open_code | `{reason}` required | Detail |
| POST `/{id}/lines/{lineId}/undo` | open_code | | Detail (Completed returns to Approved) |
| Delete draft | owner | pending action `new_product_application.delete`, entity_type `new_product_application` | countdown, hard delete |

Write: `{stock_inquiry_id?, customer_id?, customer_name?, project_name?, needed_by? (YYYY-MM-DD), remark?,
lines?: [{proposed_code?, description?, further_description?, category_id?, base_uom_id?, brand_id?,
item_type_id?, supplier_id?, supplier_item_code?, cost_price?, selling_price?, expected_qty?, remark?}]}`.
Numbers are strings or numbers; null clears.

Summary: `id, application_no, status, status_label, source, applicant_id, applicant_name, stock_inquiry_id,
stock_inquiry_number, customer_name, project_name, first_line, lines_total, lines_done, opened_codes, needed_by,
submitted_at, created_at`.
Detail = Summary + `stock_inquiry_product_code, customer_id, customer_code, remark, decided_at, decided_by,
decided_by_name, reject_reason, revise_reason, cancelled_at, cancel_reason, completed_at, updated_at, lines[]`;
line = Write line + `id, line_no, category_code, category_name, base_uom_code, base_uom_name, brand_name,
item_type_name, supplier_code, supplier_name, opened_product_id, opened_product_code, opened_product_name,
opened_product_active, closed_reason, resolved_by, resolved_by_name, resolved_at` (money as "185.00", qty as "55").

Portal, base `/api/v1/public/portal` (X-Portal-Token, grant `new_product_application`, 403
`FORM_TYPE_NOT_VISIBLE` without it): GET/POST `/submissions/new_product_application` (list answers
`{data, total, page, limit}`), GET/PUT `/submissions/new_product_application/{id}`, POST `.../{id}/submit`,
`.../{id}/revise {reason}`, `.../{id}/cancel`; GET `/new-product-application/inquiries` (own responded),
`/new-product-application/prefill?stock_inquiry_id=` (own responded only, else 404),
`/new-product-application/lookups/{item-groups|uoms|brands|item-types}?q=` (`[{id, code, name}]`),
`/new-product-application/customers?q=`. Portal lines have NO supplier_*/cost_price keys and refuse them (422)
while `PORTAL_SUPPLIER_AND_COST` is off (crew PQ1 (b)).

## v4: the paper layout (owner 18 Oct: D1-D4 yes, PQ1 yes; flow unchanged)

Source: mock `mockups/new-product-application-v4.html` (owner "Ok" 18 Oct 12:14) and crew's masked layout spec of the
company's paper NPA form (outside the repo; no value from it is committed). UAC: AC-NPA-70..79. Rebuilt locally from
fbe04604 because the cloud lane's v4 commits never reached GitHub; the design follows that lane's posted plan
(PR #1769 comments, 18 Oct 04:21 / 04:24 / 04:36).

### Field map (paper label -> column; nothing renamed in the DB)

| Paper row | Column | Who writes |
|---|---|---|
| REFF | `application_no` (screen); file-name stem (Excel) | system |
| DATE | `created_at` (MYT) | system |
| SALES PERSON | applicant (staff user) / contact (portal-raised) | system |
| STOCK INQUIRY (app only) | `stock_inquiry_id` | applicant |
| per product: PRODUCT CODE | line `proposed_code` | applicant |
| PRODUCT TYPE * | line `description` (the only required field) | applicant |
| DIMENSION / MATERIAL / THICKNESS / PACKING | line `dimension` / `material` / `thickness` / `packing` (NEW, text) | applicant |
| BRAND | line `brand_id` (clearable picker) | applicant |
| IMAGE | `entity_attachment_links` rows, `entity_type = "new_product_application_line"` | applicant |
| QTY | line `expected_qty` | applicant |
| OPENED AS (app only) | line `opened_product_id` / `closed_reason` (unchanged) | purchasing (`open_code`) |
| CUSTOMER / PROJECT / TARGET DELIVERY / REMARK | `customer_id`+`customer_name` / `project_name` / `needed_by` / `remark` | applicant |
| PURCHASING FEEDBACK: COST | line `cost_price` (one per product) | purchasing (`open_code`) |
| PURCHASING FEEDBACK: LEADTIME | `lead_time` (NEW, text, one per application) | purchasing (`open_code`) |

D3: `category_id`, `base_uom_id`, `item_type_id`, `supplier_id`, `supplier_item_code`, `selling_price`,
`further_description` and line `remark` stay in the DB (nullable, no drop) but leave every write body. Item group,
base UOM, selling price and supplier are set in AutoCount when purchasing opens the code, so they come from the
product linked at purchasing's step (`services/new_product_application_service.py:466` `link_line`): `Product.category_id`,
`base_uom_id`, `list_price` are NOT NULL (`models/product.py:241,269,280`); supplier = the product's
`product_suppliers` row with `is_primary_supplier` first, then oldest (`models/procurement.py:96-116`). Read-only.

### Data (migration `npa_0002_paper_layout`, parent `npa_0001_new_product_apps`, additive, `IF NOT EXISTS`)

- `new_product_application_lines`: `dimension`, `material`, `thickness`, `packing` TEXT NULL.
- `new_product_applications`: `lead_time` TEXT NULL, `feedback_by` VARCHAR(100) -> users SET NULL (same as
  `decided_by`, `models/new_product_application.py:85`), `feedback_at` TIMESTAMP NULL.
- Same idempotent DDL to `crew/state/migrations/NEW-PRODUCT-APP-L.sql` for the shared dev DB.

### BE

- Write schema (`schemas/new_product_application.py:15,31`, shared staff + portal): header `stock_inquiry_id,
  customer_id, customer_name, project_name, needed_by, remark`; line `id?, proposed_code, description, dimension,
  material, thickness, packing, brand_id, expected_qty`; `extra="forbid"` so any other key is 422 naming the field.
- `_apply` (`svc :221`) keeps lines by id (update / insert / delete-with-image-links), renumbers `line_no` by body order;
  a line id of another application is 422.
- `validate_submit` (`svc :326`): at least one product; each has `description` -> "Product N: enter the product type."
- `save_feedback` + `PUT /{id}/feedback` `{lead_time?, lines?: [{id, cost_price}]}`: `open_code`, Approved or Completed
  (409 else), stamps `feedback_by/at`, audited, no status change, no notification.
- `revise` (`svc :399`) clears `lead_time`, every `cost_price`, `feedback_by/at`.
- Images: `POST /{id}/lines/{line_id}/images` (multipart, jpeg/png/webp only) reusing
  `entity_attachment_service.create_response_attachment` (`:613`, gains an `uploader_kind` kwarg for the portal);
  `POST /{id}/lines/{line_id}/images/copy {attachment_id}` links an attachment already linked to the application's
  stock inquiry (`link_existing_attachment` `:179`); `DELETE /{id}/lines/{line_id}/images/{link_id}` unlinks only
  (attachment row kept, as `delete_inquiry_attachment`). Owner only, unlocked statuses only (`assert_unlocked`).
  Portal: same three under `BASE/{id}/lines/{line_id}/images...`, own application only.
  The copy picker reads `GET /inquiry-attachments?stock_inquiry_id=` (`create`; image attachments linked to that
  inquiry: `[{attachment_id, filename, url, content_type}]`) and portal `GET OWN/inquiry-attachments?stock_inquiry_id=`
  (own responded inquiry only, 404 otherwise). FE: `getStockInquiryAttachmentsForNpa(stockInquiryId)`.
- `serialize_detail` (`svc :779`): line gains `dimension, material, thickness, packing, images[]
  ({link_id, attachment_id, filename, url, content_type})`, and from the linked product `opened_category_name,
  opened_base_uom_name, opened_list_price, opened_supplier_name`; header gains `lead_time, feedback_by_name,
  feedback_at`. Portal (PQ1): `cost_price`, `lead_time`, `opened_supplier_name` shown; item group / UOM / list price
  not sent. `PORTAL_SUPPLIER_AND_COST` and `PORTAL_HIDDEN_LINE_FIELDS` (`svc :70,:82`) go.
- `npa_xlsx.py` (new, `services/`): `to_xlsx(db, app) -> (bytes, filename)`; openpyxl like
  `scm/proforma_invoice_service.py:2378` (reuse `_xlsx_safe_text` `:2365`); one sheet per product ("Product N"),
  rows in the paper's order (UAC AC-NPA-77); first image embedded via Pillow, capped at 40 MP, else the file name.
  Routes `GET /{id}/download` (whoever can view) and portal `GET BASE/{id}/download`, `Response` +
  `content_disposition` like `api/v1/scm/proforma_invoices.py:368-382`.
- Unused lookups go: staff `GET /item-types`, portal `lookups/{item-groups|uoms|item-types}` (brands stays).

### FE

- One sheet component `components/common/NewProductApplicationSheet.tsx` (+ `ProductBlock`) replaces
  `NewProductApplicationLines.tsx`; used by the staff Form + Detail and the portal form, view and edit identical
  (labels swap to inputs in place). Bordered 2-column label:value table; labels stack above values under 640 px.
- Staff detail: OPENED AS row per product (existing `OpenedAs`, `NewProductApplicationDetail.tsx:141-290`) plus a
  read-only "From AutoCount" line once linked; PURCHASING FEEDBACK inline editable for `open_code` on
  Approved / Completed with "Save feedback"; gear item "Download Excel".
- Images: the IMAGE row lists thumbnails + "Add image" (upload) + "Copy from the inquiry" (picker over the inquiry's
  attachments). On a not-yet-saved draft the picks are staged and sent right after the create returns line ids.
- Portal form/view: same sheet, COST / LEADTIME / supplier read-only (PQ1), Download Excel.
- Download through `lib/save-blob.ts` + `filenameFromContentDisposition` (as `proformaInvoiceService.ts:704`).

### Test list v4 (tester, red first; coder may not weaken assertions)

pytest `tests/test_new_product_application.py` + `tests/test_portal_new_product_application.py`: one test per
AC-NPA-70..77 (refused keys per field, lines kept by id + images survive an edit, other-application line id 422,
submit message, feedback permission/status/stamps/no status change, revise clears feedback, images type/lock/owner/
copy-only-from-own-inquiry/unlink keeps attachment, D3 read-only values + primary supplier order, portal PQ1 keys
present and staff-only keys absent, xlsx sheet count/row labels/REFF/file name/formula-safe/no image fallback,
portal download own-only 404); `tests/test_migration_npa_0002_paper_layout.py` (id <= 32, one head, every new model
column in the DDL). Existing tests that send removed keys are rewritten to the v4 contract by the tester.
vitest: sheet labels + order, Product N of M add/remove, PRODUCT TYPE required marker, no cost input for the
applicant, feedback editable only for open_code on Approved/Completed, portal shows cost/lead time/supplier read-only,
staged images on a new draft, Download Excel calls the service.
Global guards: `test_schema_uuid_id_principle.py`, `test_list_pagination_limit.py`, `test_company_scope.py`.

## v5: table form like Stock Inquiry, attachments like other forms (owner hand test FAIL, 20 Oct)

Owner on 01cc94009f: "for the product fill in, i prefer it to look like stock inquiry, instead of cards form, it is
like table form ... attachment also should be supported like other forms ... using shared components and logic, it is
just another form with different fields". Flow, permissions, D2/D3/PQ1 rules, Excel layout and migration unchanged.
Component map: PR #1769 crew-note 6280058877. UAC: AC-NPA-80..83 (supersede AC-NPA-73 and AC-NPA-79).

- Header: Stock Inquiry's `ProductInquiryFormLayout` + `InquiryFormTableRow` + `InquiryReadValue`
  (`stock-inquiries/components/ProductInquiryFormLayout.tsx:5,29,60`), title NEW PRODUCT APPLICATION.
- Products: one line table shared by staff and portal (`components/common/NewProductApplicationLines.tsx`, built on
  `components/ui/data-grid*.tsx` like the PR/SF lines, read view `PanelDataGrid`); columns No., Product code,
  Product type *, Dimension, Material, Thickness, Packing, Brand, Qty; staff detail adds Cost (MYR) (feedback) and
  Opened as (+ From AutoCount). Phone: sideways scroll inside the card, as PR/SF.
- PURCHASING FEEDBACK: LEADTIME as a table row under the header rows; COST is the per-row Cost column; editable in
  place for `open_code` on Approved / Completed with Save feedback (rules of AC-NPA-74 unchanged).
- Attachments per application, `entity_type = "new_product_application"`:
  staff `POST /{id}/attachments {attachment_id}` (link from the attachment library through
  `LinkAttachmentBrowserDialog`, as Stock Inquiry) and `DELETE /attachments/{link_id}`; portal through the generic
  `POST /public/portal/attachments` with kind `new_product_application` (`AttachmentDropzone`, pending files on create,
  as Price Tag Request), list and delete via the generic portal routes, own application only. Detail carries
  `attachments[]`.
- Removed: `NewProductApplicationSheet.tsx`, per-product image routes (3 staff + 3 portal), inquiry-attachments routes,
  copy-from-inquiry, per-line `images` in the payloads.
- Excel: the IMAGE row of every product sheet embeds the application's first image attachment (thumbnail first, the
  10 MB / 40 MP / formats rules unchanged); none -> empty.
