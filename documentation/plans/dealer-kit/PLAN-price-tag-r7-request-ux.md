# PLAN - Price Tag Request UX Round 7 (request form, assignment, portal design view)

Status: Planned 8 Sep 2026, awaiting Phase 1
UAC: `documentation/plans/dealer-kit/price-tag-r7-request-ux-acceptance-criteria.md`
Predecessor: `documentation/plans/dealer-kit/PLAN-price-tag-r6.md` (merged #734)
Branch: `feat/price-tag-r7-request-ux`, worktree `.claude/worktrees/price-tag-r7`, stack FE :3081 / BE :8081

Owner walked the salesperson journey on live (8 Sep 2026) and found the request side
lagging the designer. Rulings taken in the session, all final:

- R1 Promotion picker STAYS. Selling price comes from the promotion engine (offer price),
  exactly as today. A header-level List / Selling mode replaces the per-line switch.
- R2 Lifecycle unchanged: salesperson approval step stays. "Proof" is renamed "Design" in
  every label. Enum values are NOT renamed.
- R3 Auto-assign on submit to the person the form SLA resolves. Assigned = designing at
  once, no Claim. Claim remains only for a request the SLA could not place.

All line refs are `origin/main` at 970166643.

## What exists (measured)

- Portal form `sorento_crm_frontend/app/(auth)/portal/components/PriceTagRequestForm.tsx`
  (1614 lines). Read view and edit form both wrap in `w-full max-w-2xl mx-auto` (`:754`,
  `:1061`), a 672px cap with no wider breakpoint. Fields `:1074-1233`: Debtor, Promotion,
  Needed by, Notes, Lines (Item, Qty, Alternatives `SearchableMultiSelect`, Accessories
  text, per-line "Promo price" switch shown only when a promotion is set), Purchase Order
  `AttachmentDropzone kind="price_tag_request"` (`:1223`).
- Model `sorento_crm_backend/app/models/price_tag.py`: `PriceTagRequest` `:80-150`
  (`debtor_code`, `debtor_name`, `promotion_id`, `needed_by_date`, `notes`, `status`,
  `assigned_to_id`, `po_extraction_result` JSONB written nowhere). `PriceTagRequestLine`
  `:153-208` (`show_promo_price` bool default true, `quantity`, `alternatives` JSONB,
  `included_accessories` Text, `marketing_price_override`).
- Pricing: `resolve_prices(db, products, viewer, promotion_id)`
  `app/services/dealer_kit/pricing.py:190-236`. `lib/dealer-kit/product-block.ts:263-270`
  `priceBadgeInput`: `offerPrice = line.show_promo_price ? line.sell_price : null`.
  `price_badge` layers pick `sell_price` slot when a promo price exists (`:439,504,583`).
- Status labels `sorento_crm_frontend/lib/price-tag-status.ts:21` (`proof_ready: 'Proof
  Ready'`). CTA "Mark proof ready" in `priceTagRequestActions.ts` + `RequestTagDesigner`.
  CRM detail Proof tab `PriceTagRequestDetail.tsx:645-666` is `proofSummary()` text only.
- Submit `app/api/v1/public/portal_price_tag.py:257-300`: sets `STATUS_NEW`, calls
  `emit_form_event(db, "price_tag_request", id, "submit", contact_id=...)`. The form SLA
  orchestrator opens a tracker and resolves a tier-1 assignee (pin -> round robin ->
  coverage redirect, `form_sla_service.py:975-1000`) onto `SLATracker.assigned_to_id`.
  Nothing copies that onto `PriceTagRequest.assigned_to_id`; only Claim
  (`price_tag_requests.py:146-195`) does, then transitions new -> designing.
- Portal proof: `ProofPreviewSection` (`PriceTagRequestForm.tsx:1509-1612`) builds a
  HARDCODED mock `TagSheetDoc` (two text layers per line) and never fetches the design.
  `PriceTagProofViewer.tsx:25` `ZOOM_LEVELS = [0.2..0.6]`. CRM design endpoint
  `GET /dealer-kit/price-tag-requests/{id}/design` (`price_tag_requests.py:332-365`)
  returns the page's `draft_doc`; `transition_status` snapshots a version at proof_ready
  (`price_tag_request_service.py:214-219`).
- Export: `POST /dealer-kit/price-tag-requests/{id}/export` -> `request_tag_sheet_export`
  (`tag_sheet_export_service.py:87-`), status must be approved|ready, enqueues
  `generate_tag_sheet_pdf` on RQ `catalogue_render`, `UserDownload kind
  dealer_kit_tag_sheet_pdf`. Portal gear "Download PDF" (`PriceTagRequestForm.tsx:768-794`)
  disabled until `has_completed_export`; download route
  `portal_price_tag.py:137-183`. Arrange "Print sheet N" = same export scoped to one sheet.
- AI prefill engine exists and is already on the portal: `AIExtractService`
  (`app/services/ai_extract/extract_service.py`), route `POST
  /api/v1/public/portal/ai-extract` (`api/v1/public/ai_extract.py`), FE
  `AIExtractDialog` (`portal/components/AIExtractDialog.tsx`) via
  `aiExtractFromFiles(formKey, files)` (`portal/lib/portal-client.ts:1065`). Returns
  `ExtractResult.products: [{product_code, product_name, quantity, unit_price, total,
  notes}]` when `form_key in FORMS_WITH_LINE_ITEMS` (`form_schema_registry.py`).
  Nothing registers `price_tag_request`.

## Decisions

- D1 Labels: "Debtor" -> "Customer" (portal form, portal read view, CRM detail Request tab,
  CRM listing column, designer header). "Needed by" -> "Need by". Column names unchanged.
- D2 Width: `max-w-2xl` -> `max-w-5xl` on both wrappers; lines table gets the width. 375px
  layout unchanged (single column, horizontal scroll inside the table only).
- D3 Alternatives + Accessories removed from the portal form, portal read view lines table
  and CRM Lines tab. Columns, schema fields and canvas slot bindings stay (existing rows
  keep their data; slots render empty). No migration, no template change.
- D4 "Purchase Order" -> "Sales Order" wherever the section or tab is titled ("PO
  Attachments" tab -> "Sales Order", "No PO files attached." -> "No sales order files
  attached.", `POCrossCheckViewer` title). Attachment kind string stays.
- D5 Header `price_mode` on `price_tag_requests`: `VARCHAR(16) NOT NULL DEFAULT 'list'`,
  values `list | selling`. Portal form: a two-option segmented control under Promotion,
  "List price" / "Selling price". `selling` requires a promotion: FE disables the option
  with a tooltip until a promotion is picked; BE `validate_submittable` rejects
  `selling` without `promotion_id` (422 `PRICE_MODE_NEEDS_PROMOTION`). Per-line "Promo
  price" switch removed from the form. On every line save the service sets
  `show_promo_price = (price_mode == 'selling')`, so canvas, PDF and
  `priceBadgeInput` need no change. Lines already saved re-derive on the header save.
- D6 Line `remarks`: `TEXT NULL` on `price_tag_request_lines`. Portal form column
  "Remarks" (single-line input, placeholder none), portal read view column, CRM Lines tab
  column, designer LinesRail second row (muted, truncated, title attr). Migration
  `ptag_0005_price_mode_remarks` adds both D5 and D6 columns.
- D7 AI extract of sales order lines: register `price_tag_request` in `FORM_SCHEMAS`
  (fields: `customer_name` text, `so_number` text) and `FORMS_WITH_LINE_ITEMS`. Portal
  form Sales Order section gains "Extract lines with AI" (reuses `AIExtractDialog`, kind
  `price_tag_request`). Apply = append one line per extracted product whose
  `product_code` resolves to a product or set by exact code (case-insensitive, trimmed;
  reuse the existing item picker's lookup endpoint), qty from `quantity` (default 1),
  remarks from `notes`. Unmatched codes shown in the dialog's result table as "Not found"
  and skipped. `unit_price` is displayed in the dialog only, never stored (ADR 0008).
  Synchronous call like the other portal forms; no worker.
- D8 Auto-assign: `portal_submit_price_tag_request` after `emit_form_event` reads the
  tracker for (`price_tag_request`, id); when `tracker.assigned_to_id` is set, copies it
  onto `req.assigned_to_id` and calls `transition_status(..., STATUS_DESIGNING,
  user_id=assignee)`. No tracker or no assignee = stays `new` unclaimed, Claim as today.
  Failure inside this block logs and leaves the request `new` (same posture as the SLA
  emit). Existing assignee notification is the SLA's (`notify_assignee`), nothing new.
- D9 "Proof" -> "Design" in labels: `proof_ready` label "Design Ready"; CTA "Mark design
  ready"; `proofSummary` sentences; portal section "Design preview"; changes-requested
  copy. Enum values, routes, table names unchanged.
- D10 CRM detail Proof tab removed. Tabs: Request, Lines, Sales Order.
- D11 Portal design preview renders the REAL design: new `GET
  /api/v1/public/portal/submissions/price_tag_request/{id}/design` returning the same
  payload as the CRM design endpoint (draft doc + resolved line data), owner-gated
  (`_require_own_request`) and status-gated to `proof_ready | changes_requested |
  approved | ready` (404 otherwise, no doc leak while designing). FE replaces the mock
  with `TagSheetRenderer` over that doc. Zoom levels `[0.25, 0.5, 0.75, 1, 1.5, 2]` plus
  "Fit" (width of the container); default Fit; pinch/ctrl-wheel not in scope.
- D13 SLA config admin offers Price Tag Request. Prod has NO `form_sla_configs` row for
  `price_tag_request` (owner, 8 Sep) and the admin dialog
  `sla-management/form-sla-config/components/FormSLAConfigDialog.tsx:121-126` lists only
  stock_inquiry, purchase_request, sponsorship_form, complaint, so the row cannot be
  created from the UI. Add `price_tag_request` to that list, to `FormSLASourceType`
  (`_shared/formSLAService.ts:48`), the label map(s) and the list filter. No backend
  change: `FORM_SLA_TYPES` already carries it. After deploy the owner creates the config
  (start event `submit`, marketing agent) and D8 starts placing requests.
- D12 Auto-export on approve: `transition_status` to `approved` calls
  `request_tag_sheet_export(db, request_id, sheet_ids=None, user_id=...)` after commit of
  the status. Portal "Download PDF" enables when the export completes (worker). While
  pending the gear item reads "PDF is being generated". CRM "Export PDF" stays for
  re-exports.

## Slices (one lane, one PR, commit per slice)

| # | Slice | Layer | Files |
|---|---|---|---|
| S1 | Labels, width, remove alternatives/accessories, Sales Order rename, Design Ready, drop Proof tab (D1-D4, D9, D10) | FE | `PriceTagRequestForm.tsx`, `PriceTagRequestDetail.tsx`, `PriceTagRequestsList.tsx`, `lib/price-tag-status.ts`, `priceTagRequestActions.ts`, `RequestTagDesigner.tsx`, `POCrossCheckViewer.tsx`, `LinesRail` |
| S2 | Header price mode + line remarks (D5, D6) | FE mock -> BE | migration `ptag_0005`, model, schemas, `price_tag_request_service.py` (derive show_promo_price), portal + CRM routes, `PriceTagRequestForm.tsx`, CRM Lines tab, LinesRail |
| S3 | Auto-assign on submit (D8) | BE | `portal_price_tag.py`, `price_tag_request_service.py` |
| S4 | Portal design preview real doc + zoom (D11) | FE mock -> BE | `portal_price_tag.py` (new route), `portal-client.ts`, `PriceTagRequestForm.tsx`, `PriceTagProofViewer.tsx` |
| S5 | Auto-export on approve (D12) | BE + FE copy | `price_tag_request_service.py`, `tag_sheet_export_service.py`, gear item copy |
| S6 | AI extract sales order lines (D7) | BE registry + FE | `form_schema_registry.py`, `PriceTagRequestForm.tsx`, `AIExtractDialog.tsx` kind map |
| S7 | Price Tag Request selectable in Form SLA config admin (D13) | FE | `FormSLAConfigDialog.tsx`, `formSLAService.ts`, `FormSLAConfigList.tsx` |

Phase 1 (FE against mocks, no tests): S1, S2 FE, S4 FE, S6 FE, S7.
Phase 2 (BE test-first, then vitest for FE): S2 BE, S3, S4 BE, S5, S6 registry; vitest for
form (price mode gating, remarks, no alt/acc columns), proof viewer zoom, status labels.
Phase 3: `/code-review`, browser evidence to `seed-assets/verification/r7-*.png`.

## Out of scope (named triggers)

- Renaming enum values `proof_ready` etc. Trigger: a reporting consumer reads the raw value.
- Dropping `alternatives` / `included_accessories` columns and slots. Trigger: templates
  with those slots are retired.
- Async / worker-backed extraction. Trigger: a sales order over the sync route's page cap.
- Portal-triggered export button. Auto-export on approve covers the ask.
- Pinch-zoom on the portal preview.
