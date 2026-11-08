# UAC: Quotation Certification tab (QUOTE-CERT-TAB)

Status: owner answered card Q1-Q5 = (a) on 8 Nov ~10:40 MYT; mock approved (pending crew's real-PDF
matcher run). Plan: `PLAN-quote-cert-tab-08nov.md`. Card: `CARD-quote-cert-tab-08nov.md`.

## Contract (binding for tester and coder)

### Data (one additive migration `qcert_0001_quote_certificates`, chained on main's head)

- `certificate_products.model_code` VARCHAR(60) NULL. Text exactly as printed on the certificate.
- `certificate_products.model_code_source` VARCHAR(10) NULL, CHECK `ai|manual`: `ai` = Suggested
  (from the ingest or the PDF suggestion, CERT-14), `manual` = typed or confirmed by a person.
- `certificate_products.boxes` JSONB NULL. The product-certificate DEFAULT box cache:
  `{"revision_id": str, "code": str, "source": "auto"|"manual", "has_text": bool, "boxes": [Box]}`.
- `projects.quotation_document_certificates` (company-scoped like its document):
  `id` uuid pk, `company_id`, `document_id` FK `projects.quotation_documents` CASCADE,
  `certificate_id` FK `certificates` CASCADE, `included` bool NOT NULL default true,
  `source` VARCHAR(10) NOT NULL `auto|manual` (CHECK), `send_to_customer` bool NULL
  (NULL = default rule CERT-9), `boxes` JSONB NULL (per-quote override:
  `{"revision_id": str, "boxes": [Box]}`), `created_at`, `created_by`, `updated_at`;
  UNIQUE (`document_id`, `certificate_id`). A row exists only when a user changed something.
- `projects.quotation_issues.certificates` JSONB NULL: the frozen list at issue (CERT-11).

`Box` = `{"page": int >= 1, "x": float, "y": float, "w": float, "h": float, "product_id": str|null}`.
x/y/w/h are FRACTIONS (0..1) of the page AS DISPLAYED (rotation applied), origin top-left. All four
within [0, 1], w > 0, h > 0, x + w <= 1, y + h <= 1 (422 `certificate_box_invalid` otherwise). At most
200 boxes per write.

### Matcher (`app/services/certificate_pdf_service.py`, pure functions over PDF bytes)

- `find_boxes(pdf_bytes, code) -> {"has_text": bool, "boxes": [Box without product_id]}`.
  Whole-token, NORMALISED (real-PDF finding, crew 8 Nov): normalise = lower-case, drop spaces,
  hyphens and the punctuation `.,;:()[]/`. A hit is a run of 1 to 4 CONSECUTIVE words in reading
  order (`page.get_text("words")` sorted by block, line, word; a run may cross a line break, e.g.
  `WC` / `8355`) whose joined normalised text EQUALS the normalised code, starting and ending on word
  boundaries. So `WC 8355` hits `WC 8355`, `WC8355,` and `WC-8355`; `WB 151` never hits `WB 1515`;
  `14A` never hits `114A` or `14AB`. The box is the union of the run's row bands. Row band = nearest horizontal ruled line at/above the hit and at/below it
  (from `page.get_drawings()`, thin lines or rect edges), x span = outermost vertical rules of the
  table; no rules = the hit line widened by 2 pt. Every hit on every page is returned.
- `has_text` false when the whole document yields no text characters (scan); then `boxes` is [].
- Symbol-font decode (crew prod run, 8 Nov): before has_text, matching and suggestion, every character
  in U+F020..U+F0FF is shifted back by 0xF000 (28 of 40 text SPAN files and all text WELPS/WEPLS
  files store their text that way).
- Unreadable / encrypted PDF: `has_text` false, no exception.
- `suggest_code(pdf_bytes, product_code) -> str|None`: the printed code for a product (CERT-14):
  among word runs of 1 to 3 consecutive words whose normalised text has length >= 3 and contains a
  digit (a 3-character run needs a letter AND a digit: `14A` yes, `120` no), and is a substring of the normalised product code, the LONGEST normalised run wins (ties:
  first in reading order); returned as printed (words joined by one space, edge punctuation
  stripped). None when nothing qualifies or there is no text.
- `is_number_only(code) -> bool`: normalised code is all digits.
- `burn_boxes(pdf_bytes, boxes) -> bytes`: a COPY with each box drawn as a red (0.88, 0.11, 0.28)
  1.5 pt rectangle; input bytes unchanged.

### Routes (base `/api/v1/projects/{project_id}/quotation-documents/{document_id}/certificates`)

Reads: `READ` of `app/api/v1/projects/quotation_documents.py:68` (+ API key) and the project/document
404 chain the spec sheet routes use. Writes: `EDIT` + `_editable_project` (exactly like
`spec_sheet.py`). Defaults writes additionally need `master_data.certificates.edit`.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `` | | `{"can_edit": bool, "can_edit_defaults": bool, "items": [Row]}` |
| POST | `` | `{"certificate_id"}` | 201 `Row` (manual add, or re-include a removed one) |
| GET | `/{certificate_id}` | | `Detail` |
| GET | `/{certificate_id}/file` | | `application/pdf` bytes of the current revision (inline) |
| PUT | `/{certificate_id}/boxes` | `{"scope": "quote"|"default", "boxes": [Box]}` | `Detail` |
| DELETE | `/{certificate_id}/boxes` | `?scope=quote` | `Detail` (drops the quote override) |
| PATCH | `/{certificate_id}` | `{"send_to_customer": bool|null}` | `Row` |
| POST | `/export` | `{"issue_id": str|null}` | 202 `{"download_id"}` queued like `generate_quotation_issue_pdf` |

Remove is a pending action, not a route: `record_actions` key `quotation_certificate.remove`,
entity type `quotation_certificate`, payload `{"entity_id": <document_id>, "certificate_id"}`,
`WINDOW_REVERSIBLE`, permission `projects.projects.edit`, park-time AND commit-time check = edit
right + write access to the project + certificate currently listed.

Coverage code (master data, `app/api/v1/master_data/certificates.py`):
`PATCH /api/v1/master-data/certificates/{certificate_id}/products/{coverage_id}` body
`{"model_code": str|null}` (trimmed, max 60, "" = null), permission `master_data.certificates.edit`;
coverage rows in the certificate detail payload gain `model_code`.

`Row` = `{certificate_id (the row's representative, CERT-15), also_filed_as: [{certificate_id, scheme, certificate_number}], scheme, certificate_number, title, certifying_body, valid_until,
validity_state ("valid"|"expiring"|"expired"|"unknown"), source ("auto"|"manual"),
products: [{product_id, product_code}], marked: {count: int, state: "found"|"edited"|"none"|
"no_text"|"not_found"|"no_file"|"suggested"|"code_needed"}, send_to_customer: bool (effective), has_file: bool}`.

`Detail` = `Row` + `{revision_id, page_count|null, has_text, can_edit, can_edit_defaults,
box_source ("quote"|"default"), boxes: [Box], products: [{product_id, product_code,
coverage_id, model_code, model_code_source ("ai"|"manual"|null), code_used, number_only: bool,
state ("found"|"suggested"|"edited"|"not_found"|"no_text"|"code_needed")}]}`.

### Rules

- CERT-1 List = distinct certificates (status `active`) linked by `certificate_products` to any
  product on the CURRENT draft versions of the document (`project_spec_sheet_service._draft_version_ids`),
  a set line contributing every part's product (`set_parts_snapshot[].product_id`); plus
  `quotation_document_certificates` rows with `included` and `source=manual`; minus rows with
  `included=false`. Ordered by scheme, then number. Company scope of the document applies.
- CERT-2 One Row per certificate; `products` lists every quoted product it covers (code order).
- CERT-3 Code used per product = `model_code` when set; else (text PDF) the CERT-14 suggestion,
  persisted; else none (state `code_needed`, no box). The product code itself is NOT searched (real
  certificates never print it). Matching per the matcher rule above. A code with `number_only` true
  is flagged, never blocked.
- CERT-4 Boxes resolution for (quote, certificate): quote override when its `revision_id` equals
  the current revision; else per covered quoted product: `certificate_products.boxes` when its
  `revision_id` is current (and, for `source=auto`, its `code` equals the code used); else
  `find_boxes` on the current file, written back to `certificate_products.boxes` as `source=auto`.
  A manual-added certificate covering no quoted product has no boxes.
- CERT-5 `marked.state` (first that applies): `no_file` (current revision has no attachment), `edited`
  (a person drew boxes, so a scan with boxes reads edited), `no_text` (scan),
  `suggested` (count > 0 and any box from an
  `ai` code), `found` (count > 0), `code_needed` (a covered product has no code), `not_found`
  (text PDF, products present, zero hits), `none` (no quoted product covered).
- CERT-6 PUT boxes `scope=quote` writes the override for the current revision (any quote editor).
  `scope=default` needs `master_data.certificates.edit` (403 otherwise), requires every box to carry
  a `product_id` that is covered by this certificate AND quoted on this document (422
  `certificate_box_product_invalid`), writes `certificate_products.boxes` with `source=manual` per
  product (a product with no boxes in the payload gets `boxes: []`), and drops this quote's override.
- CERT-7 Changing `model_code` resets that coverage row's cached boxes (next read re-finds).
- CERT-8 Add: certificate must be `active` and visible in the caller's company scope (404
  `certificate_not_found` otherwise); adding one already listed returns it unchanged (201, no dup).
  Remove then commits `included=false` (auto) or deletes the row (manual).
- CERT-9 Effective `send_to_customer`: the stored value when not NULL, else
  `validity_state != "expired"` and `has_file`.
- CERT-10 `/file` serves only a certificate currently on the list (404 otherwise), never another
  attachment; content type `application/pdf`, `Content-Disposition: inline`.
- CERT-11 Issuing freezes on `quotation_issues.certificates` the list of rows with effective
  `send_to_customer` = true: `[{certificate_id, revision_id, attachment_id, scheme,
  certificate_number, boxes}]`. Later edits never change an issued snapshot.
- CERT-12 Export with `issue_id` uses that issue's snapshot; without it, the live list. Output
  `"<document no> <rev> Certificates.pdf"` (draft: `"<document no> Certificates.pdf"`), every
  certificate in list order with boxes burned in (`burn_boxes`), stored files untouched, into My
  Downloads like the quote PDF. A certificate whose file cannot be read is skipped and named in the
  job result. Zero certificates = 422 `quotation_certificates_empty`.
- CERT-14 Suggested code: when a coverage row has no `model_code` and the current file has text,
  the first read stores `model_code = suggest_code(...)`, `model_code_source = 'ai'`. The ingest
  (`_link_via_certificate`, `app/api/v1/external/product_attachments.py:217`) stores the printed
  `requested_code` of each matched product the same way unless `via == prefix` or the row already
  has a `manual` code (never overwritten). A product whose code is `ai` shows `state = suggested`
  when its boxes are found. PATCH coverage `{model_code}` (typed) and `{"confirm": true}` (keep the
  suggested text) both set `model_code_source = 'manual'`; both need `master_data.certificates.edit`.
  Suggested boxes ARE sent to the customer, drawn like confirmed ones (owner 8 Nov, sub-question (i));
  the tab flags "Suggested, check" before sending.
- CERT-15 Dedupe by file: certificates on the list whose current revision's file is the same
  (`attachments.file_hash` equal, else same `attachment_id`) form ONE Row. Representative = valid
  before expired, then latest `valid_until`, then scheme, number; the others go in `also_filed_as`.
  Boxes, override and `send_to_customer` are keyed by the representative; Remove writes
  `included=false` for every member; the export carries the file once; `products` is the union.
- CERT-16 Verified listing (owner 8 Nov ~11:05, "cert a"): an AUTO row (not added by hand) whose
  current file has text, where NO covered quoted product has its code found (all products
  `not_found` / `code_needed`) and no box exists (no quote override, no manual default), is listed
  with `verified: false`, `marked.state = "not_on_certificate"`, rendered greyed with the text
  "Not found on certificate", and its effective `send_to_customer` is false unless the stored value
  is true (a person ticked Include). Drawing a box (quote override or default) makes it
  `verified: true`. Scanned files (`no_text`), files missing, links with `certificate_products.source
  = manual`, and hand-added rows are always `verified: true`. Verified rows sort before unverified.
  `Row` gains `verified: bool`. The Master Data link clean-up report is a separate lane.
- CERT-13 Removing a quoted product drops its auto certificate from the list on next read; manual
  and removed markers persist.

### Frontend

- FE-1 New last tab "Certification" (`QuotationDocumentTabs.tsx`), page `(view)/certification`.
- FE-2 `PanelDataGrid` list, listing key `projects.projects.view::quotation-certificates`, columns
  per mock screen 1 with explicit sizes, row click opens the certificate page; toolbar: "Download
  certificates PDF" + "Add certificate" (edit only). Empty state heading "No certificates", hint
  "None of the quoted products has a certificate on file." Remove = row menu, deferred
  `quotation_certificate.remove` with the 5 s countdown (no confirm dialog).
- FE-3 Certificate page `[documentId]/certification/[certificateId]`: `PdfViewer` with `loadData`
  from `/file` and a new optional `overlay` render prop per page that draws `Box`es as % of the
  page; Draw box (pointer drag on the page), move, resize (corner), remove; side panel products with
  "Code on certificate" (editable only with `can_edit_defaults`), save scope segmented control
  ("This quote only" / "Every quote (this product)", the second disabled without
  `can_edit_defaults`), "Include in the certificates PDF" checkbox.
- FE-4 Add dialog: `SearchableSelect` of certificates (existing `useCertificates`), clearable.
- FE-5 Certificates detail page covered products: "Code on certificate" column, inline edit with
  `master_data.certificates.edit`.
- FE-6 WhatsApp dialog lists "<no> <rev> Certificates.pdf (n)" with Download when the issue's
  snapshot has n > 0.
- FE-7 No UUIDs shown, no explanatory copy, no em/en dashes, usable at 375 and 1280.

## Acceptance tests (tester writes these red first)

Backend (Postgres, seed own chain, `ZZT` prefixes):
1. Matcher on a generated ruled table: `14A` -> exactly one box covering the wrapped row; `114A`,
   `14AB` rows not hit; `WC 8355` hits `WC 8355`, `WC8355,`, `WC-8355` and `WC` / `8355` across a
   line break; `WB 151` hits nothing next to `WB 1515`; `suggest_code` (WB 1515 for SRTWB1515, WC 8355
   for SRTWC8355-RL, AB 7049 over 7049 for SRTAB7049, None for no candidate); `is_number_only`; code absent -> []; image-only PDF -> has_text false; multi-word code;
   case-insensitive; code on 2 pages -> 2 boxes; rotated page (90) box fractions still cover the
   row as displayed; garbage bytes -> has_text false, no raise.
2. `burn_boxes` returns different bytes with one more drawing per box; input unchanged.
3. GET list: distinct certs, shared cert one row with 2 products, set-line parts counted,
   archived certificate excluded, other company's coverage excluded, removed excluded,
   manual included, order.
4. POST add (201, idempotent, 404 inactive/foreign), pending remove commits included=false / deletes manual.
5. Dedupe CERT-15 (two certificates, same file_hash -> one Row, representative rule, remove hides both,
   export once); suggested code persisted on first read and never overwriting manual; ingest stores
   requested_code (not for prefix); PATCH confirm/typed -> manual, 403 without certificates.edit.
   Boxes resolution order CERT-4 incl. revision change invalidating override and cache; model_code
   change resets cache; `marked.state` each value.
6. PUT boxes: quote scope by quote editor; default scope 403 without certificates.edit; 422 bad box /
   foreign product; default write drops quote override.
7. `/file` 404 for certificate not on list; 200 pdf otherwise. Permission: 403 without READ, write
   routes 403 without EDIT.
8. Issue freezes snapshot; later edit does not change it; expired excluded unless send_to_customer
   true.
9. Export: snapshot vs live; 422 empty; filename.
10. Migration up/down idempotent on an empty DB; single alembic head.

Frontend (vitest): tab present in order; list renders rows/badges/empty state; overlay maps a Box
to % style on the page; draw/move/resize produce correct fractions (clamped to [0,1]); save scope
disabled without `can_edit_defaults`; add dialog calls service; remove uses the pending-action hook.
