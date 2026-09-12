# UAC - Portal journey round 8: verify card, landing toolbar, price tag request sections

Plan: `documentation/plans/portal/PLAN-portal-price-tag-journey-r8.md`
Status: Approved 12 Sep 2026; building

## Journey

Actor: a dealer salesperson on a phone (mostly) or a desktop browser, arriving from the
WhatsApp link the CRM sent them.

1. **Verify.** The card shows the masked number they will get the code on, a
   "Not your number?" link directly under it, the code box, and one Resend button. The
   sixth digit verifies. Nothing else on the card. Decision: none (type the code).
2. **Landing.** Header reads "Welcome, <name>" with Log out at the right edge of the
   content column. No banner. The content column is capped at 768px and centred, so on
   a 27-inch screen the search box is a column, not a ribbon. Under the search box: the
   form-type picker (unchanged). Under that, one toolbar row: Filter, Sort, view toggle on
   the left; New <type> on the right. Decision: which form type (already there).
3. **Find a submission.** Filter offers every field the chosen type's card carries
   (status, customer, product, project, need-by, created), with the values actually
   present in the list; Sort offers the same fields, either direction. Card or compact
   row view, remembered on this device. Decision: none beyond the pick.
4. **Duplicate.** From a card's long-press / right-click preview or from a detail
   page's menu, "Duplicate" opens a NEW draft of the same type with every field and line
   copied, attachments empty. Nothing is saved until Save draft / Submit. Decision: none.
5. **New price tag request.** Four sections, top to bottom: Customer; Sales Order &
   Lines; Price; Additional Information. Only Customer is open. Picking a customer opens Sales
   Order & Lines. Dropping the sales order there shows its thumbnail with its own
   "Extract" action; the AI dialog opens straight on that file's results table where any
   row can be removed; Confirm and prefill appends the lines. Add line stays for manual
   rows. The first line opens Price. Choosing a price mode opens Additional Information
   (Need by and Notes, both optional); Selling price also reveals the optional Promotion
   picker inside Price. Any collapsed section opens by tapping its header at any
   time, and a collapsed section shows a one-line summary of what is in it. Decision per
   section: one.
6. **Submitted request.** Same four sections, read-only, all open, with the Sales
   Order thumbnails previewable. An "Edit" CTA in the header while the status is New or
   Changes requested; editing swaps values for inputs in place and Save writes without
   re-submitting or restarting the SLA. At Designing / Design ready the header CTA is
   "Request changes" (existing). Approved / Ready: no edit.

Stakeholders told automatically: nobody new. A post-submit edit is audited; the
assigned designer sees the new values on next open (no notification in this round;
trigger named in the plan).

## Phase 1 (FE against mocks)

### Verify card

- **AC-V1 [FE]** Given the OTP card, when it renders, then the order is: title "Verify
  your identity"; line "We'll send a code to your WhatsApp <masked>"; link "Not your
  number?" directly under it; label + 6-digit code input; Resend button. The intro alert
  ("Verify with a one-time code..."), the "Code sent. It expires in 10 minutes..." line,
  the "Verify and continue" button and the "No code after a minute?" WhatsApp box are not
  rendered.
- **AC-V2 [FE]** Given six digits typed or pasted, when the sixth lands, then verification
  fires without a button (existing behaviour kept) and a wrong code still shows the inline
  error under the input.
- **AC-V3 [FE]** Given `reason=logout`, when the card renders, then the "You have been
  logged out" notice is still shown (it is the one alert that survives).
- **AC-V4 [FE]** Given the legacy token route (no slug), when the card renders, then
  "Not your number?" is absent (as today) and the layout otherwise matches AC-V1.

### Landing

- **AC-L1 [FE]** Given the landing, when it renders at 2560px wide, then every block
  (header, search, picker, toolbar, list) sits inside one centred column no wider than
  768px; Log out is at the right edge of that column. At 375px the column is full width
  with the existing 12px side padding.
- **AC-L2 [FE]** The bookmark banner (`BookmarkHint`) is not rendered anywhere and its
  Copy link / Share buttons and the Cmd+D text are gone.
- **AC-L3 [FE]** Given the search row, when it renders, then it holds the search input
  only; the status Filter icon button beside it is gone.
- **AC-L4 [FE]** Given a form type is selected, when the list renders, then a toolbar row
  above it shows, left to right: Filter, Sort, view toggle; and New <type> at the right.
  At 375px the four controls fit on one row without clipping (icon-only Filter / Sort with
  `aria-label`s and tooltips; New keeps its label).
- **AC-L5 [FE]** Given the Filter button, when tapped, then a popover lists one control
  per filterable field of the current type (table in the plan, D-L4), every one a dropdown
  select: status as a single clearable select of the statuses present; each text field as a
  single clearable select of the distinct values present in the loaded rows; each date field
  as From / To. Applying narrows the
  list client-side; the Filter button shows a count badge of active filters; "Clear all"
  resets.
- **AC-L6 [FE]** Given the Sort button, when tapped, then a menu lists the sortable fields
  of the current type, each with ascending / descending; default is Created, newest
  first; the number field is labelled "Form Number"; the active choice is ticked and the button label reads the field name at
  ≥768px.
- **AC-L7 [FE]** Given the view toggle, when set to List, then each submission renders as
  exactly one line (number, status pill, the type's primary meta, need-by when present,
  created date); a long cell truncates with a `title` and never wraps the row and the choice persists in localStorage per device; the default is Cards
  under 768px and List at 768px and up. Switching type keeps the choice.
- **AC-L8 [FE]** Given any filter active OR a search term, when zero rows result, then the
  empty state reads "No submissions match your filters." with a "Clear filters" action that
  clears both.

### Duplicate

- **AC-D1 [FE]** Given a submission card, when long-pressed / right-clicked, then the
  preview dialog offers "Duplicate" beside Open (and Revise when offered). Given the view
  page of any of the five types, when its gear dropdown opens, then "Duplicate" is listed
  (the four legacy views gain the gear; the price tag gear gains the item).
- **AC-D2 [FE]** Given Duplicate on a stock inquiry / purchase request / sponsorship /
  complaint, when tapped, then the form opens at `/<type>/new?from=<id>` in NEW mode with
  every field and every product / complaint line copied from the source, attachments
  empty, no draft row created until Save draft or Submit.
- **AC-D3 [FE]** Given Duplicate on a price tag request, when tapped, then the new form
  opens with customer, price mode, promotion, need by, notes and lines copied, Sales Order
  attachments empty, Customer and Sales Order & Lines and Price sections open (they hold
  values), Additional Information open too (it holds values).
- **AC-D4 [FE]** Given `?from=` names a submission the contact does not own or that
  does not exist, when the form loads, then a toast reads "Could not copy that
  submission." and the form opens empty.

### Price tag request form

- **AC-P1 [FE]** Given the new form, when it renders, then four section cards appear in
  order: Customer; Sales Order & Lines; Price; Additional Information. Customer is open; the
  other three are collapsed with their headers visible.
- **AC-P2 [FE]** Given a collapsed section, when its header is tapped or receives
  Enter/Space, then it opens; tapping again collapses it. `aria-expanded` reflects the
  state.
- **AC-P3 [FE]** Given no customer, when a customer is picked, then Sales Order & Lines
  opens automatically (Customer stays open). Auto-open happens once per section per
  form load; a section the user collapsed by hand is not re-opened by the rule.
- **AC-P4 [FE]** Given Sales Order & Lines open with no attachment, when it renders, then
  the dropzone reads "Drop the sales order here, paste a screenshot, or" with Choose file
  / Paste from clipboard, and the lines table shows "No lines yet." with Add line.
- **AC-P5 [FE]** Given one or more files attached in Sales Order & Lines, when they
  render, then each shows as a thumbnail tile (image preview or file icon + name) with its
  own "Extract" action (labelled "Extract with AI from <filename>"); no section-level
  extract button exists.
- **AC-P6 [FE]** Given a tile's Extract action tapped, when the dialog opens, then it skips
  its upload stage and shows the results table for THAT file only (loading state while
  extracting). Each result row has a remove control; removing drops the row from what
  Confirm and prefill applies. Confirm and prefill appends one line per remaining
  matched row (existing code / qty / remarks mapping). Unmatched rows stay labelled "Not
  found" and are skipped.
- **AC-P7 [FE]** Given zero lines, when the first line lands (from AI or Add line), then
  Price opens automatically.
- **AC-P8 [FE]** Given Price open, when it renders, then it holds the List / Selling
  segmented control only. Selecting either mode opens Additional Information. Selecting
  Selling price reveals the Promotion `SearchableSelect` inside Price, labelled optional.
  Switching back to List hides Promotion and clears it. Selling with no promotion submits
  (owner ruling: the r7 submit rule is dropped).
- **AC-P8b [FE]** Given Additional Information, when it renders, then Need by and Notes are
  both optional (no asterisk) and Submit proceeds with both empty.
- **AC-P9 [FE]** Given a collapsed section that holds values, when it renders, then its
  header shows a one-line summary: Customer -> the customer name; Sales Order & Lines ->
  "<n> lines, <m> files"; Price -> "List price" or "Selling price - <promotion>"; Need by
  & Notes -> the date (and "notes" when notes exist). Empty sections show no summary.
- **AC-P10 [FE]** Given Submit tapped with Customer, at least one line and a price mode,
  then submit proceeds as today. Given any of those missing,
  then the first offending section opens and the field error shows inline; no toast-only
  failure.
- **AC-P11 [FE]** Given the detail (read) view, when it renders, then the same four
  sections appear in the same order, all open, values as text, Sales Order attachments as
  the same thumbnail tiles as the form and each opens `AttachmentPreviewModal`. Nothing on
  the read view is actionable beyond preview: no drop area, no paste, no tile remove, no
  tile Extract, no Add line. The
  design preview card stays below them where it is today.
- **AC-P12 [FE]** Given status New or Changes requested, when the detail header renders,
  then a primary "Edit" button shows; tapping it swaps each value for its input in place
  (same sections, same order) with Save / Cancel in the header, and only then do the drop
  area, tile remove, tile Extract and Add line become available. Given status Designing or
  Design ready, then the header shows no Edit button (existing Request changes / Approve
  actions unchanged). Given Approved / Ready / Void, no Edit.
- **AC-P13 [FE]** Given Edit mode, when Save is tapped, then the request is written via
  PUT, the view returns to read mode showing the saved values, status unchanged, and a
  toast "Saved" shows. Cancel restores the values shown before Edit.
- **AC-P14 [FE]** Given the form at 375px and at 1280px, when each section is open, then
  nothing clips; the lines table scrolls horizontally inside its card at 375px only.

### Motion [UX]

Frequency: a dealer opens the portal a few times a day and the form a few times a week
(occasional band in `DESIGN-LANGUAGE.md`). Section expand / collapse is a row-expand
gesture (tens/day band): no height animation.

- **AC-U1 [UX]** Section open / close: no animation at all (`animate-none` both ways); the
  body appears and disappears instantly, on tap and on Enter / Space alike.
- **AC-U2 [UX]** Filter popover and Sort menu use the shared Popover / DropdownMenu
  surfaces and their existing presets; nothing new is animated. Keyboard-opened surfaces
  do not animate (M2-01).
- **AC-U3 [UX]** Buttons keep the shared pressed state (`:active` scale from the primitive);
  the view toggle, Filter and Sort get no extra motion.
- **No-motion list:** auto-open of the next section (the rule fires while the user is
  typing or picking; a slide here would steal attention), collapsed-header summaries,
  card <-> list switch, list re-order after sort, the Edit -> inputs swap.

## Phase 2 (BE, test-first)

- **AC-B1 [BE][T]** Given a price tag request with `portal_draft_at` NULL and status
  `new` or `changes_requested`, when the owning contact PUTs
  `/api/v1/public/portal/submissions/price_tag_request/{id}`, then 200, the header fields
  and lines are replaced, `status`, `assigned_to_id`, `portal_draft_at` and the SLA
  tracker are unchanged, no form event is emitted, and an audit row records the edit.
- **AC-B2 [BE][T]** Given status `designing`, `proof_ready`, `approved`, `ready` or
  `void`, when the owning contact PUTs, then 409 `NOT_EDITABLE`.
- **AC-B3 [BE][T]** Given a request owned by another contact, when PUT, then 403/404 as
  today (owner gate unchanged).
- **AC-B4 [BE][T]** Given a submitted request (not draft), when POST `.../submit` is
  called again, then 409 `NOT_DRAFT` as today (a post-submit edit can never re-fire the
  SLA).
- **AC-B5 [BE][T]** Given a draft with `price_mode = selling` and no `promotion_id`, when
  POST `.../submit`, then 200 and every line has `show_promo_price = true` (the rule
  `PRICE_MODE_NEEDS_PROMOTION` no longer exists).
- **AC-B10 [BE][T]** Given a post-submit PUT, then: `needed_by_date` as a date serialises
  into the audit row (200, not 500); `lines: []` -> 422; a set-guarded line -> 422; a line
  carrying a marketing price override keeps it; a `promotion_id` outside the contact's
  audience -> 422; the audit row is `UPDATE` with description "portal edit after submit",
  `company_id`, `old_values` (header + lines) and `new_values` (payload incl. lines).
- **AC-B11 [BE][T]** Given a price tag request that is not editable (approved, ready, void,
  designing, proof_ready), when the contact POSTs an attachment or DELETEs an attachment link
  on it, then 409; at new / changes_requested / draft both succeed.
- **AC-B12 [BE][T]** Given `needed_by_date: ""` on PUT, then it is stored NULL and submit
  succeeds.
- **AC-B9 [BE][T]** Given a draft with customer, one line and a price mode but no
  `needed_by_date`, when POST `.../submit`, then 200 (need by is optional).
- **AC-B6 [BE][T]** Given the detail GET, when the request is `new` or
  `changes_requested` and not a draft, then the body carries `is_editable: true`; every
  other post-submit status carries `false`; drafts carry `true`. (The FE Edit button
  reads this, never the status list.)
- **AC-B7 [FE][T]** Vitest: verify card renders per AC-V1 (no removed strings present,
  auto-verify still fires); landing filter derives options from rows, sort orders rows,
  view choice persists; duplicate prefill from `?from=`; price tag section auto-open
  rules (AC-P3, P7, P8) and Edit gating on `is_editable`.
- **AC-B8 [E2E]** agent-browser evidence run, from `/portal/c/<slug>` by clicks: verify
  card; landing at 375px and 2560px; filter + sort + list view; duplicate a purchase
  request; new price tag request through all four sections with an AI extract and a
  row removed; submit; Edit on the submitted request; Save.

## Out of scope (triggers in the plan)

Server-side filter / sort / paging; a bookmark mechanism; notifying the designer on a
post-submit edit; duplicating attachments; a generic schema endpoint for portal forms.
