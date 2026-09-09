# PLAN - supplier documents, proforma invoice first (9 Sep 2026)

**Status:** APPROVED by the captain, 9 Sep 2026 ("go"), one lavish markup round. UAC:
`scm-supplier-documents-pi-first-acceptance-criteria.md`. Rulings so far (captain, 9 Sep): PI lines
mirror the PI document; supplier packing rows stored on the PI; a packing list with no PI is refused;
Incoming Containers page removed; `PI-YYMM-NNN` 3 digits monthly; old derived names lose their
supplier reference; **A** for the carton split (our packing list carries two lines of one product
from one supplier, because the printed list must). Round 1 (lavish): rows placed whole at convert;
PI number takes the upload month; Jiexia stays one PI per container block; incoming routes deleted
where nothing else calls them; container / seal / BL carried from the packing rows onto the draft;
upload keeps the SCM two-step Test → Confirm (no read on drop); the n8n route never rewrites lines
of a converted draft. One lane, one branch, one PR.

## Journey

See the UAC. Actor: purchasing, desktop, a few uploads a week. Fewest decisions: supplier once per
upload; which PI a packing list attaches to only when the file states no invoice number and shares
no date; a Dismiss per unknown supplier code, once. Everything else is derived.

## What was measured (9 Sep)

| Fact | Where |
| --- | --- |
| Supplier packing-list upload creates OUR shipment, `in_transit` | `supplier_document_service.apply` → `packing_list_service.apply` → `create_shipment`; `InboundShipmentCreate.shipment_status` defaults `"in_transit"` (`app/schemas/procurement.py:301`), the PL path never sets it. Only convert forces `draft` (`proforma_invoice_service.py:89`). This is the screenshot's In Transit row. |
| Two births for our packing list | Convert (draft) and the supplier-document dialog (in transit). The dialog is mounted on Packing Lists, Proforma Invoices and `/scm/incoming`. |
| PI number = supplier's, verbatim | `pi_number_for` (`proforma_invoice_service.py:121-156`); no number stated → `PI-<filename stem>-<block>`. Unique identity (company, supplier, pi_number). |
| Running numbers already exist | `document_numbering_rules` per company, `NumberingService.get_next_number(doc_type, reference_date, company_id)`; the packing-list draft rule is one seed row `PL-{yy}{month:02d}-`, 3 digits, monthly (`numbering_defaults.py:26-30`); FE page System Management → Running Numbers. |
| PI lines already carry packing columns | `cartons, pcs_per_carton, carton_l/w/h_cm, cbm_per_unit, cbm_total, net_weight, gross_weight, material` (migration 435). |
| Supplier PL grain ≠ PI grain | Kailu: 11 PI lines, 12 PL rows (SRTSC14-GM 85 = 50 + 35). Jiexia PL: lid and fitting rows absent from the PI. Jinbaichuan: one sheet holds both, RMB in cols 17-18, three filler rows. |
| Dismiss ruling exists | `supplier_code_alias_service.dismiss` → `source='dismissed'`, both targets NULL (`scm.py:1276-1294`); route `POST /scm/supplier-code-aliases/dismiss` (`fulfilment.py:328`). PI apply does not yet read it (`grep dismissed` in `proforma_invoice_service.py` = 0 hits). |
| Alias engine exists, invisible | `import_field_alias` (doc_type, field, alias, locale), `AliasResolver.for_doc_type`; 113 aliases for `proforma_invoice`, 44 for `packing_list` on the dev DB; seeded by migrations only; no API, no page. |
| Our shipment lines: one per (shipment, product, supplier) | `uk_inbound_shipment_lines_ship_prod_sup` (`procurement.py:401-415`, migration 374). Convert groups by that key; `update_shipment` refuses a duplicate 409; `_upsert_shipment_lines` warns in its own comment that it must refuse rather than guess if the index changes. |
| GRN + SPO never keyed on the line | `SPOAllocation` holds `inbound_shipment_id + product_id`, no line id (`procurement.py:420-539`); `grn_spo_matching.py` has zero `InboundShipmentLine` references. |
| Pre-existing per-line bug | `refresh_shipment_line_statuses` stamps the PRODUCT's allocated and received totals onto every line of that product (`procurement_service.py:1126-1130` CAVEAT, backlogged lane D of the 6 Sep plan; same caveat `container_request_service.py:125-134`). `incoming_stock_service._unallocated_quantity` and `allocation_suggestion_service` read those per-line figures. Rare today, routine under ruling A. |
| Incoming Containers is already off the sidebar | `menu.config.test.ts:52-58` `INTENTIONALLY_REMOVED_PATHS = {'/scm/incoming'}`; reached by deep URL only. Its `AllocationPanel` is a different component from project-sales'. |
| Consolidated export, capacity, split card are per line | `consolidated_packing_list.build` groups by supplier and appends per line; `container_capacity` sums per line; FE `packingListLineMath.ts` per line. Safe under A. |

## Design

### S1. Our PI number

- `scm.proforma_invoice.supplier_ref` String(100) nullable. `pi_number` becomes ours.
- Seed row `doc_type='proforma_invoice'`, `prefix_template='PI-{yy}{month:02d}-'`, `number_digits=3`,
  `reset_policy='monthly'`, per company, through `numbering_defaults.py` (same shape as
  `seed_inbound_shipment_draft_rule`, and the same lazy per-company creation the PL rule got when a
  new company had none). Mint at insert with `NumberingService.get_next_number(...,
  reference_date=today, company_id=...)` in the apply transaction.
- `pi_number_for` → `supplier_ref_for`: the stated number, suffixed by container when one file yields
  two blocks with one number (Jiexia), else NULL. The derived `PI-<stem>-<n>` name is retired.
- Update-in-place key = (company, supplier, supplier_ref); a NULL ref never matches, so a file with no
  number needs `file_as_new` (refusal `supplier_ref_missing`, shown in the preview with the existing
  "file as new" toggle).
- Migration (alembic, one revision): add column; `UPDATE supplier_ref = pi_number WHERE pi_number NOT
  LIKE 'PI-%-%'` for the derived ones set NULL (the derived form is `PI-<stem>-<int>`; test the regex
  on the dev DB before applying: `^PI-.+-\d+$`); then per company, rows ordered by `created_at, id`,
  month key from `created_at`, mint sequentially and stamp; write the rule row with `next_value` and
  `last_reset_key` at the resulting state. Rebuild `uq_scm_proforma_invoice_identity` on
  `(company_id, supplier_id, supplier_ref)` (NULLS DISTINCT default) and add
  `uq_scm_proforma_invoice_number (company_id, pi_number)`.
- FE: list column, search, header meta, `display_document_number` unchanged for revisions. Running
  Numbers page needs nothing: it lists whatever rules exist.

### S2. Supplier packing rows on the PI

- Table `scm.proforma_invoice_packing_line` (UAC B1). One row per supplier packing-list row,
  verbatim, plus `product_id`/`product_set_id` (resolved through the alias table as PI lines are),
  `proforma_invoice_line_id` (the PI line whose product it is), `match_state`. Company-scoped like
  the PI line. Trigger for a table rather than columns: the grains differ today (Kailu 12 vs 11,
  Jiexia rows absent from the PI) and the rows are what convert writes (S4).
- Reading: `packing_list_reader.read_workbook` stays the reader (44 aliases already cover Kailu and
  Jiexia; Jinbaichuan's `尺寸（mm）`, `孔距`, `认证编码` are the unmapped headers S5 will surface, and
  the preview shows them from S2 on because S5's `unmapped_headers` field is produced by the same
  resolver call). Combined sheet: one read yields lines AND rows (the PI reader takes the priced
  columns, the PL reader the packing columns, from the same header map).
- `supplier_document_service.apply` order: PI files → packing files → combined. A packing file
  resolves its PI (UAC B5) and `replace_packing_rows(db, pi, rows)`: delete old rows, insert, match
  rows to lines by product, apply dismissed aliases, roll up (UAC B8). The same function backs
  "Attach packing list" from the PI detail (dialog opened with `attachTo` locked).
- Roll-up rule is one function `_rollup_packing(line, rows)`: sums for cartons, cbm_total,
  net/gross totals; shared-or-NULL for pcs_per_carton and dims. Runs after every packing write and
  on packing-row dismiss/undo.
- Source files: `file_supplier_document` already files the xlsx as an Attachment; link it to the PI
  (entity = `proforma_invoice`, the generic attachment linkage this repo already has for other
  entities) instead of to a shipment. PI detail General tab lists them (UAC B14).
- Routes: `GET /scm/proforma-invoices/{id}` gains `packing_lines[]` and `packing_file{name, uploaded_at}`;
  `POST/DELETE /scm/proforma-invoices/{id}/packing-lines/{row_id}/dismiss`;
  `POST /scm/proforma-invoices/{id}/packing-lines/{row_id}/match` reuses the line-match body
  (product or set) and writes the manual alias through the same `_remember_line_match` path.
  The dialog keeps `useTwoStepUpload`: choosing files reads nothing, **Test** runs preview,
  **Confirm** applies. `/supplier-documents/preview` per-file adds `kind`, `attach_to{id, pi_number, how: 'invoice_number'|'date'|null}`,
  `refusal{code, message}`. `/supplier-documents/apply` body gains `attach_to` per file.
- FE: Packing tab (UAC B9-B12) on `ProformaInvoiceDetail`, Packed column on Lines (B11), the dialog's
  Attaches-to select and refusal row (B13). Hooks: `useProformaInvoicePackingMutations`
  (dismiss / undo / match) on the shared mutation pattern; service functions in
  `proformaInvoiceService.ts`; the deferred Dismiss uses `useDeferredRowAction` as Forget does.

### S3. One birth for our packing list

- Delete `packing_list_service.apply`, `_match_prices`, the R14 link-writing path, the
  `ProformaInvoiceShipmentLink` writes from the supplier-document path, and `_block_notes` if only
  that path used it. Keep `packing_list_reader`, `file_supplier_document`, `_products_by_code`.
- Packing Lists page: remove the gear item and the `PackingListUploadDialog` mount + state. The
  dialog file moves to `scm/proforma-invoices/components/SupplierDocumentsUploadDialog.tsx` (its
  only remaining home) and the `ProformaUploadDialog` alias comment goes.
- Delete `app/(protected)/scm/incoming/` and the `menu.config.test.ts` rows. Backend: keep
  `GET /scm/inbound-shipments` (packing-lists list uses it); delete the consolidated-packing-list
  and allocation-panel routes only if a grep of FE + MCP catalog shows no other caller (coder
  reports the grep in the commit).
- No status patch: with the path gone, nothing but convert (draft), manual create, and the n8n
  external route (in transit, deliberately: that is a forwarder's real packing list) creates a
  shipment.

### S4. The carton split on our packing list (ruling A)

- Migration: drop `uk_inbound_shipment_lines_ship_prod_sup`, create
  `ix_inbound_shipment_lines_ship_prod_sup` non-unique on the same columns. Downgrade = 374's merge.
- Convert (`convert_to_draft_shipment`): grouping changes from (product, supplier) to
  "one shipment line per matched packing row; PI lines without rows keep the (product, supplier)
  group". Line columns per UAC D2. Link rows unchanged in shape.
- `update_shipment`: remove `_duplicate_line_product_id`; `_upsert_shipment_lines` claims by id
  first, then by (product, supplier) only when exactly one existing line holds it, else 409
  `line_id_required`; drop the `_merge_shipment_lines` call on update. External create route keeps
  its own per-product sum and `_merge_shipment_lines`.
- Apportion (`_apportion(total, lines)` in `procurement_service.py`): walk lines in
  (created_at, id) order, each takes `min(remaining, quantity_shipped)`, the last takes any
  overflow. `refresh_shipment_line_statuses` uses it for both `spo_allocated_quantity` and
  `quantity_received`. Retire the two CAVEAT comments. Cost stamping at `procurement_service.py:3018`
  keeps its ordered `.first()`: split lines from one PI line share one price, so the pick is
  harmless; comment updated to say why.
- Placement is whole rows (`packing_row_ids`, default all unplaced); `line_quantities` only for PI
  lines without rows. Header carry-over: one container across the selected PIs' rows → container,
  seal, BL prefilled on the draft; a conflict leaves them blank and is named in the response.
- External n8n route on an existing shipment WITH PI links: header only, lines untouched, reason
  logged. Without links: today's per-product replacement. `_upsert_shipment_lines`' id-first rule
  therefore never meets an id-less payload against split lines.
- FE: packing-list Lines grid drops the duplicate-product guard; convert dialog shows rows (whole
  placement), the carried header, and the conflict line.

### S5. Import column mappings, visible and editable

- BE: `app/api/v1/system/import_field_aliases.py` (list grouped, create, delete, fields per doc type),
  `import_alias_service.canonical_fields(doc_type)` built from each reader's declared field set
  (readers already name the fields they `get`; expose that list, do not hand-type it).
  Permissions `system.import_field_aliases.view/.edit` in `permission_registry.py`, grant sweep to
  the roles holding `system.numbering_rules.*`.
- `AliasResolver` gains `unmapped_headers(header_row)`: normalised header cells that resolve to no
  field. Both readers call it once per block; preview carries it per file.
- FE: `system-management/import-field-aliases/` copied from `companies/` (list + `FormDialog`), nav
  entry under Running Numbers, `RequireAccess`. Upload preview "Unmapped headers" chips with
  "Map to…" (`SearchableSelect` of the field list) → create → re-preview that file.

### Not built, and why

- No mapping "engine": the resolver and table exist. The lane adds an API, a page, and one field on
  the preview.
- No `packing_rows` JSON column on the PI line: the rows are what convert writes and what the tab
  edits; a table is the direct shape. Trigger named for the alternative: none.
- No per-line SPO allocation table: `SPOAllocation` stays (shipment, product); apportioning is a
  read-time rule on figures that were already derived. Trigger for a line-level allocation: an
  operator needs to allocate carton A and carton B to different SPOs. Not today.
- No PI shell from a packing list alone (ruling 3).

## Slices, order, and the captain's test list

Order: **S3 → S1 → S2 → S4 → S5.** S3 first because it deletes the code S2 would otherwise have
to keep consistent; S1 before S2 because packing attach resolves on `supplier_ref`; S4 after S2
because convert reads the rows; S5 last, independent.

Phase 1 (FE mock, one coder, worktree): S1 columns/header, S2 Packing tab + Packed column + dialog
Attaches-to/refusal, S3 removals, S4 grid guard removal, S5 page + preview chips, all against
mocked service functions with the contract at the top of `proformaInvoiceService.ts` and
`importFieldAliasService.ts`. Browser-verified by sidebar clicks at 375 and 1280.

Phase 2 (tester red first, same coder green), per slice:

| Slice | Test file | Tests (one line per AC) |
| --- | --- | --- |
| S3 | `tests/scm/test_supplier_documents_no_shipment.py` | C1 apply creates 0 shipments; C5 packing set written. Vitest: gear item gone; menu test rows removed. |
| S1 | `tests/scm/test_proforma_invoice_numbering.py` | A1 two in a month then next month resets; A2 Kailu ref / Jinbaichuan NULL; A3 re-upload keeps number, no-ref refusal; A4 backfill over 3 seeded rows in 2 months + rule state. |
| S2 | `tests/scm/test_proforma_invoice_packing_lines.py` | B2 Kailu 11/12 + roll-up numbers; B3 Jinbaichuan lines + rows + three unmatched; B4 Jiexia lid row unmatched on the right PI; B5 resolve by number, by date, by attach_to, refusal, replace; B6 dismissed alias lands dismissed; B7 dismiss + undo; B8 agree/disagree roll-up. Vitest: tab empty/populated, Packed badge, dialog prefill + refusal. |
| S4 | `tests/scm/test_proforma_invoice_convert_packing.py`, `tests/test_packing_list_split_lines.py` | D2 12 lines / two SRTSC14-GM / no-rows fallback; D3 notes; D1 insert two same-key lines; D4 edit by id, ambiguous id-less 409; D5 apportion under/exact/over; D6 unallocated 0 and 25, planner proposes 25; D7 export two rows. |
| S5 | `tests/system/test_import_field_aliases_api.py`, `tests/scm/test_supplier_documents_unmapped_headers.py` | E1 list/create/409/delete/fields/denial; E2 renamed `箱数` header reported. Vitest: page list + add; preview chip → map → refetch. |

Fixtures: the five 9 Sep files copied to `documentation/plans/scm/fixtures/` (Kailu PI + PL 260730,
Jinbaichuan, Jiexia PI + PL), plus a Jinbaichuan copy with `箱数` renamed for E2/E5.

Phase 3: reviewer + security-reviewer (file upload, permission slugs, company scoping on the new
table) + tester browser run, once, in parallel. Kill test on B5, D5, A3.

## Design brief

Surfaces: PI detail Packing tab and Lines Packed column (dense grid, a few times a week), the upload
dialog preview (same), the mappings page (rare). **Nothing new animates** (UAC F2). Countdown on
Dismiss reuses the existing deferred-action preset. Status via `Badge`; empty state via the shared
primitive with its CTA.

## Risks

- Backfill numbering on prod: rows across companies and months; run the migration's mint on a
  prod copy first, diff against the expected count per month.
- Apportion changes displayed allocated/received figures on existing multi-supplier containers
  (the only split lines that exist today). Expected and correct; note in the PR.
- `_upsert_shipment_lines` id-first claim: the FE PUT already sends line ids for existing lines
  (verify in `PackingListLinesTab` save path before Phase 2; if not, that is Phase 1 work).
- Attachment entity linkage for `proforma_invoice`: confirm the attachment model's entity columns
  accept a new entity type without a migration (grep `entity_type` constraints).

## Deviations

- **Phase 2, S3 (captain ruling 9 Sep):** `POST /scm/packing-lists/preview|apply` and
  `packing_list_service.apply` are deleted outright, with the FE `previewPackingList` /
  `applyPackingList` service functions (no caller since Phase 1 removed the incoming page). The two
  route tests in `test_fulfilment_routes.py` and the six `test_supplier_document_service.py` tests
  that assert shipment creation / price matching are retired with them: they guard the behaviour
  AC-C1 removes.
- **Phase 2, S1 (captain ruling 9 Sep):** AC-A3's `supplier_ref_missing` refusal is retired. A
  document stating no reference is always created fresh (there is nothing to match against), never
  updates in place, and `file_as_new` is irrelevant to it. The tester's `test_a3` is amended by the
  coder, on the captain's explicit authorisation, to assert that a second apply of the same
  ref-less file creates a second PI and never touches the first.
- **Phase 2, S1 (captain ruling 9 Sep):** the 24 pre-existing tests that asserted `pi_number` equals
  the supplier's stated text, or rebuilt the retired `-R2` / `-2` suffix shapes, are updated by the
  coder to the new semantics only (supplier text → `supplier_ref`; `pi_number` matches
  `PI-\d{4}-\d{3}`; a revision row mints its own number). Every other assertion in those tests stays.

## Markup round 1 (lavish, 9 Sep)

Q1 whole rows, Q2 upload month, Q3 one PI per container block, Q4 delete unused incoming routes:
all the recommended options. Captain notes: carry the container number over at convert (AC-D2c);
no read on file drop, Test button like every other upload (AC-B13, `useTwoStepUpload`); asked
whether the manual → n8n → back upload changes after the index drop: no, and AC-D4b pins that a
converted draft's lines are never rewritten by that route.
