# PLAN - Portal journey round 8: verify card, landing toolbar, price tag request sections

Status: Approved 12 Sep 2026 (owner: "ok good to go"); building
UAC: `documentation/plans/portal/portal-price-tag-journey-r8-acceptance-criteria.md`
Predecessor: `documentation/plans/dealer-kit/PLAN-price-tag-r7-request-ux.md` (merged #758)
Branch: `feat/portal-journey-r8`, worktree `.claude/worktrees/portal-journey-r8`

All line refs are `origin/main` at c385da410.

## What exists (measured)

- Verify card: one component `sorento_crm_frontend/app/(auth)/portal/components/PortalVerifyCard.tsx`
  (554 lines) behind both `/portal/verify` and `/portal/c/[slug]/verify`. Intro alert `:417-419`
  (also carries the post-logout notice), "Code sent ... 10 minutes" `:430-435`, Resend `:454-466`,
  "Verify and continue" `:467-474`, WhatsApp escape hatch `:490-510` (`data-testid="wa-escape-hatch"`),
  "Not your number?" `:512-527` (slug only). Auto-verify on the sixth digit already exists `:277-285`.
- Landing: `PortalLanding.tsx` (946 lines). Root `w-full px-3 pt-3 pb-4 space-y-3` `:443`, no
  max-width. Header `:444-459`. `BookmarkHint` `:462`. Search row + status Filter dropdown
  `:467-513` (client-side status filter, `SubmissionList` `:608-613`). Type picker
  `SearchableSelect` + default-tab star `:516-584`. `SubmissionList` `:597-660` with the New button
  `:620-628`, empty state `:629-639`, `SubmissionCard` `:665-827`, `SubmissionPreviewDialog`
  `:829-945` (Revise + Open footer).
- List data: `GET /public/portal/submissions?type=&q=` (`portal.py:759`) and
  `GET .../submissions/price_tag_request?q=` (`portal_price_tag.py:74`). Only `type` and `q`.
  Whole list per kind. Volume on the prod copy: max 30 rows per contact per kind, avg 5-8.
  Summary shape `PortalSubmissionSummary` `portal-client.ts:74-112`.
- Duplicate: no route anywhere. `SubmissionForm.tsx:636-700` already prefills fields, products and
  complaint lines from a fetched source (used by revision drafts). `portal-paths.ts:77-92`.
- Price tag form `PriceTagRequestForm.tsx` (1722 lines). `isEditable = isNew || isDraft` `:309`.
  Read view `:870-` (gear `:883-`, `h1` `:919`, Sales Order filename rows `:1037-1070`,
  `AttachmentPreviewModal` `:1072-1078`). Edit form `:1165-` : Customer `:1178`, Promotion `:1206`,
  Price segmented `:1219-1283`, Need by `:1285`, Notes `:1303`, Lines `:1315-1373`, Sales Order card
  with "Extract lines with AI" `:1375-1406`, `AIExtractDialog` `:1409`, Save draft / Submit
  `:1456-1464`. `AttachmentDropzone` (`AttachmentDropzone.tsx`, prop `disabled` `:57`) renders
  thumbnail tiles + `AttachmentPreviewModal`.
- `AIExtractDialog.tsx` (759 lines): `stage` state `'upload' | ...` `:92`; props `:19-32`
  (`open, onOpenChange, kind, fieldDefs, onApply, onExtracted?, renderRowStatus?`); product rows
  `:526-565`; Confirm and prefill `:598-602`; file tile has `onRemove` `:624-679`.
- Backend gate `_require_draft` `portal_price_tag.py:585-595` on PUT `:285`, DELETE `:318`,
  submit `:342`. Submit clears `portal_draft_at`, sets `new`, emits the form SLA event and
  auto-assigns (r7 D8). `_detail_body` `:598-`. Validator `PRICE_MODE_NEEDS_PROMOTION`
  `price_tag_request_service.py:456`.
- Shared primitives: `components/common/ListBoardViewToggle.tsx` (`value: 'list' | 'board'`,
  `onChange`), `components/ui/collapsible.tsx`, `components/ui/popover.tsx`,
  `components/ui/dropdown-menu.tsx`, `components/common/SearchableMultiSelect`.

## Decisions (owner rulings 12 Sep in bold)

- **D-V1** Verify card per the owner's demarcation: delete the intro alert (keep only the
  post-logout variant, rendered as the same `Alert` only when `reason=logout`), the "Code sent"
  line, the "Verify and continue" button and the WhatsApp escape hatch. Move "Not your number?"
  to directly under the phone line. The sixth digit verifies (existing effect). Risk accepted:
  a WhatsApp first-contact block now has only Resend as the visible recovery; trigger to revisit
  is a support ticket citing "no code".
- **D-L1 Banner gone, no copy-link, no bookmark button.** Delete `BookmarkHint.tsx` and its test.
- **D-L2 Landing column 768px, forms 1024px.** `PortalLanding` root becomes
  `w-full max-w-3xl mx-auto px-3 pt-3 pb-4 space-y-3` (also the loading / error roots `:413,:423`).
  Log out stays absolute inside that relative header, so it hugs the column edge. The price tag
  form keeps r7's `max-w-5xl`. `SubmissionForm` roots: cap at `max-w-3xl` too (measure first;
  if a kind already has a wider cap, keep the wider one and note it in the PR).
- **D-L3** Toolbar row inside `SubmissionList`, replacing the New-only row: left group
  Filter (icon + count badge), Sort (icon; label at `sm:`), `ListBoardViewToggle`; right: New.
  The search-row Filter dropdown `:476-513` is removed; its status filter lives in the popover.
- **D-L4** One descriptor table drives Filter and Sort, `portal/lib/landing-fields.ts`:

  | kind | fields (key: label, type) |
  |---|---|
  | all | `status: Status, status` / `created_at: Created, date` / `document_number: Form Number, text` |
  | stock_inquiry | `product_code: Product, text` / `project_name: Project, text` / `project_customer: Customer, text` |
  | purchase_request | `project_title: Project, text` / `customer_name: Customer, text` / `delivery_order_number: Delivery order, text` / `item_description: Item, text` |
  | sponsorship_form | `sponsor_subject: Subject, text` / `project_title: Project, text` / `customer_name: Customer, text` / `purpose: Purpose, text` |
  | complaint | `product_code: Product, text` / `project_title: Project, text` / `customer_name: Customer, text` |
  | price_tag_request | `customer_name: Customer, text` / `needed_by_date: Need by, date` |

  Filter: every control is a dropdown select (owner mark-up 12 Sep). `status` -> `SearchableSelect`
  (single, clearable) over the effective statuses present (Draft / the real status label); `text`
  -> `SearchableSelect` (single, clearable) over the distinct non-empty values present in the loaded
  rows; `date` -> From / To date inputs. Sort: every field, asc / desc; default
  `created_at desc`. State is component state (resets on reload); the view choice persists in
  `localStorage['sorento.portalView']`. Everything is client-side over the rows already fetched
  (D-L4 evidence: max 30 rows per kind per contact). Trigger for server-side: a contact over
  200 rows in one kind.
- **D-L5** List view row: `SubmissionRow` in the same file as `SubmissionCard`, EXACTLY one line
  (owner mark-up: never wrap; every cell `truncate` + `title`), same
  click / long-press / keyboard wiring (extract the handlers into a hook `useSubmissionPress`
  so the two share them). Default `board` under 768px, `list` at `md:` and up when nothing is
  stored.
- **D-D1 Duplicate copies fields + lines, not attachments.** No backend. Entry points: the
  preview dialog footer (`:924-941`) and the gear dropdown on EVERY form's view page (owner
  mark-up): price tag gear `:883-` gains "Duplicate"; `SubmissionForm` detail view gets the same
  gear icon-button + `DropdownMenu` (only item today: Duplicate) if it has no header menu. Both go
  to `portalNewPath(kind, slug) + '?from=<id>'` (new helper `portalDuplicatePath`).
  `SubmissionForm` new-mode reads `from`, fetches the source, and runs the SAME prefill block as
  `:657-700` (lift it into `applySourceToForm(source)`), then strips nothing else: new mode has no
  id, status or attachments, so nothing leaks. `PriceTagRequestForm` new-mode does the same via
  `getRequest(from)` -> header fields + `lines` (drop `id`). A 403/404 on the source -> toast
  "Could not copy that submission." and an empty form (AC-D4).
- **D-P1** Price tag form sections (AC-P1): a local `Section` component (header button with
  `aria-expanded`, optional summary, `Collapsible` body) used four times. Open state is a
  `Record<SectionKey, boolean>` plus `autoOpened: Set<SectionKey>` so a rule fires once and
  never re-opens a section the user closed (AC-P3). Rules: customer set -> `sales_order`;
  lines.length 0 -> 1 -> `price`; `priceMode === 'list'` chosen, or `selling` with
  `promotionId` -> `need_by`. Read view: same component, all open, no collapse rule
  (headers still toggle).
- **D-P2** Promotion moves INSIDE the Price section, shown only when `priceMode === 'selling'`,
  labelled optional (owner mark-up 12 Sep); switching to List hides and clears `promotionId`
  (AC-P8). The r7 "disabled until a promotion is picked" tooltip goes away: mode first, promotion
  second. **Owner ruling 12 Sep: drop the r7 D5 submit rule.** `validate_submittable` no longer
  raises `PRICE_MODE_NEEDS_PROMOTION` (`price_tag_request_service.py:450-456` removed); Selling
  with no promotion submits, `show_promo_price` still derives from `price_mode`, and with no
  offer the tag prints the list price (`resolve_prices` already answers "no offer" as
  `offer_price=None`). The FE never disables Selling.
- **D-P2b** Need by is optional (owner mark-up): drop the `needed_by_date` line from
  `validate_submittable` (`price_tag_request_service.py:432-433`); FE label loses the asterisk;
  the column is already nullable (drafts save without it; coder confirms on the model). The
  fourth section is titled "Additional Information" (Need by + Notes), both optional, so it never
  blocks Submit; it auto-opens once a price mode is chosen.
- **D-P3 Extract with AI runs PER FILE** (owner mark-up: ten files attached, one extracted).
  The Sales Order dropzone stays the single upload path. Each attachment tile carries its own
  "Extract" action (icon-button with `aria-label="Extract with AI from <filename>"`, tooltip);
  the card-header "Extract lines with AI" button `:1383-1390` is removed. `AIExtractDialog` gains
  `initialFiles?: File[]`: when given, it mounts on the results stage and calls the existing
  extract for that file at open. Files already uploaded to the server (edit of a draft) are
  fetched as bytes via `portalFetchBytes` (`portal/lib/portal-preview.ts`) into `File`s; for a
  new form the dropzone's local buffer already holds `File`s. `alsoAttach` is forced false in
  this mode (they are attached already).
- **D-P4** AI result rows removable: an "x" icon button per product row (`:544-565`), removes
  from local `productLines`; Confirm and prefill applies the remainder. Same control on the
  fields table is not needed (price tag has no header fields).
- **D-P5** Detail view attachments: replace the filename rows `:1037-1070` with
  `<AttachmentDropzone kind="price_tag_request" submissionId={id} readOnly />` so tiles, preview
  modal and ordering are the form's own (AC-P11). Read view is fully inert (owner mark-up): no
  drop area, no paste, no remove on tiles, no per-tile Extract action, no Add line, no line
  inputs, until Edit is tapped. `disabled` today may only grey things; add a `readOnly` prop on
  the shared dropzone that renders tiles + preview only.
- **D-P6 Edit at New + Changes requested.** FE: `isEditable = isNew || isDraft || request.is_editable`
  where `is_editable` is a new detail field (AC-B6). Header: "Edit" primary button when
  `request.is_editable && !isDraft`; Edit flips `editing` state which reuses the form branch
  (`:1165-`) with the header showing Save / Cancel instead of Save draft / Submit. Save ->
  `updateRequest` -> re-`getRequest` -> read mode. BE: `_require_editable(req)` passes when
  `portal_draft_at` is set OR `status in (new, changes_requested)`; PUT uses it, DELETE and
  submit keep `_require_draft`. The PUT path for a non-draft: same `update_request` service
  call (which already re-derives `show_promo_price` and validates price mode), then
  `record_audit(...)` with action `portal_edit_after_submit`; no `emit_form_event`, no status
  or assignee change. `_detail_body` adds `is_editable`. Trigger for notifying the designer:
  a designer reports designing against stale lines.
- **D-M1** No new motion beyond `--duration-fast` opacity on section bodies (AC-U1); the
  Collapsible primitive's height animation, if any, is turned off for these sections.

## Slices (one lane, one PR, commit per slice)

| # | Slice | Layer | Files |
|---|---|---|---|
| S1 | Verify card per D-V1 | FE | `PortalVerifyCard.tsx`, its test |
| S2 | Landing column cap, banner gone (D-L1, D-L2) | FE | `PortalLanding.tsx`, delete `BookmarkHint.tsx` + test, `SubmissionForm.tsx` roots |
| S3 | Toolbar: filter, sort, view toggle, list rows (D-L3, D-L4, D-L5) | FE | `PortalLanding.tsx`, new `portal/lib/landing-fields.ts`, new `portal/components/LandingToolbar.tsx` |
| S4 | Duplicate (D-D1) | FE | `portal-paths.ts`, `PortalLanding.tsx` (preview dialog), `SubmissionForm.tsx`, `PriceTagRequestForm.tsx` |
| S5 | Price tag sections + progressive open + promotion inside Price + need-by optional + summaries (D-P1, D-P2, D-P2b FE) | FE | `PriceTagRequestForm.tsx`, new `portal/components/FormSection.tsx` |
| S6 | Extract with AI on attached files + removable rows (D-P3, D-P4) | FE | `PriceTagRequestForm.tsx`, `AIExtractDialog.tsx`, `AttachmentDropzone.tsx` (expose local files) |
| S7 | Detail thumbnails + Edit CTA + Save/Cancel (D-P5, D-P6 FE, mocked `is_editable`) | FE | `PriceTagRequestForm.tsx`, `price-tag-request-service.ts` |
| S8 | Post-submit edit route gate + `is_editable` + need-by and promotion optional on submit (D-P6 BE, D-P2 BE, D-P2b BE) | BE, test-first | `portal_price_tag.py`, `price_tag_request_service.py`, `tests/test_portal_price_tag_edit.py` |
| S9 | Vitest for S1, S3, S4, S5, S7 (AC-B7) | FE tests | tester writes red first |

Phase 1: S1-S7 against mocks (S7 mocks `is_editable` in the service).
Phase 2: tester red tests for S8 + S9, then the same coder makes them green and swaps the S7 mock.
Phase 3: reviewer + security-reviewer (the PUT gate is an auth surface) + agent-browser evidence
(AC-B8) to `documentation/plans/portal/evidence/r8/`.

## Test list (captain's, one line per AC the tester writes)

- test_put_new_not_draft_updates_and_keeps_status (B1)
- test_put_changes_requested_updates (B1)
- test_put_designing_409_not_editable, ..._proof_ready, ..._approved, ..._ready, ..._void (B2)
- test_put_other_contact_denied (B3)
- test_submit_twice_409_not_draft (B4)
- test_submit_selling_without_promotion_succeeds (B5)
- test_detail_is_editable_matrix (B6)
- test_submit_without_needed_by_succeeds (B9)
- vitest: PortalVerifyCard.r8.test.tsx (V1-V4); LandingToolbar.test.tsx (L5-L8);
  PortalLanding.viewToggle.test.tsx (L7); SubmissionForm.duplicate.test.tsx (D2, D4);
  PriceTagRequestForm.sections.test.tsx (P1-P3, P7-P9); PriceTagRequestForm.edit.test.tsx (P12-P13)

## Out of scope (named triggers)

- Server-side filter / sort / paging - trigger: a contact over 200 rows in one kind.
- Bookmark mechanism - owner ruling: none.
- Notify the designer on a post-submit edit - trigger: a stale-lines report.
- Duplicating attachments - trigger: a dealer asks for it twice.
- A schema endpoint for portal forms - trigger: a second consumer of the field list.
