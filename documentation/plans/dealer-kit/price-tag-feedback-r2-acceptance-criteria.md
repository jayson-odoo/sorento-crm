# Price Tag Feedback R2 - Acceptance Criteria

Status: Approved 1 Sep 2026
Plan: `documentation/plans/dealer-kit/PLAN-price-tag-feedback-r2.md`

## Journey

**A - salesperson requests tags (portal).** Salesperson opens the portal, starts a
New Price Tag Request, picks dealer / needed-by / lines, drops PO files into the
dropzone, submits. The files travel with the request. Reopening the request later
shows exactly the form they filled, read-only, PO files listed and openable, and
once the proof is exported, the PDF is downloadable from a gear menu.

**B - marketing designs the tags (CRM).** Marketing opens the request, sees the
lines AND the PO attachments, clicks Design Price Tags, and the canvas always
opens: a matching published template pre-clones the tag; with no template the line
starts from a product-block starter bound to that line's product. No silent
"Preparing this line...". Full screen is one click.

**C - marketing maintains templates (CRM).** Designer works full screen, drops a
product block, resizes text boxes without the font changing, pulls session guides
off the rulers, adds a barcode layer that resolves each product's EAN at render,
previews any block (or the whole tag) via an eye on the block itself, saves drafts
freely and Publishes when ready - request designers only ever see published
versions.

---

## Lane A - live bugs

### S1 - PO attachments end-to-end

- **AC-S1-1 [FE]** Given the portal New Price Tag Request form with no draft yet,
  when the salesperson drops a PDF into the PO dropzone, then the file is buffered
  and listed as pending (blob preview), not discarded.
- **AC-S1-2 [FE]** Given buffered pending files, when Save Draft or Submit
  succeeds, then every pending file is uploaded to the created request and appears
  as an uploaded attachment; a failed file shows a named error toast and stays
  pending.
- **AC-S1-3 [FE]** Given an existing draft, when a file is dropped, then it
  uploads immediately (no save needed) and renders in the list with preview.
- **AC-S1-4 [BE]** Given a portal token owning request R, when
  `POST /api/v1/public/portal/attachments` is called with
  `kind=price_tag_request, submission_id=R`, then the file is stored via
  `EntityAttachmentService` with `entity_type='price_tag_request'` and the
  response matches the legacy kinds' shape. A token NOT owning R gets 404.
- **AC-S1-5 [BE]** Given a request with attachments, when the portal detail
  (`GET /portal/submissions/price_tag_request/{id}`) or the CRM detail
  (`GET /dealer-kit/price-tag-requests/{id}`) is fetched, then `attachments`
  carries id, filename, content type, url; asserted in a route test (the
  `response_model` must declare it).
- **AC-S1-6 [FE]** Given a request with attachments, when marketing opens the CRM
  detail, then the PO Attachments card lists the files with working
  preview/download - no upload controls.
- **AC-S1-7 [FE]** Given a draft with an uploaded attachment, when the
  salesperson removes it (confirmation first), then the link is deleted via the
  generic delete route and the list updates.
- **AC-S1-8 [E2E]** Portal submit with 1 PO file -> CRM detail shows the file ->
  portal read-only shows the file (agent-browser evidence run).

### S2 - portal read-only parity + real Download PDF

- **AC-S2-1 [FE]** Given a submitted (non-editable, non-proof) request, when the
  salesperson opens it, then the page renders the SAME sections in the SAME order
  as the edit form (debtor, promotion, needed-by, notes, lines table, PO files),
  every input swapped in place for its read-only value. `RequestDetailView` is
  deleted.
- **AC-S2-2 [FE]** Given proof-review statuses, when opened, then the same
  read-only layout renders with the proof section beneath it (existing proof UI
  unchanged).
- **AC-S2-3 [FE]** Given a request in `ready`/`approved` with a completed export,
  when the salesperson opens the gear dropdown, then Download PDF fetches the real
  exported file; with no completed export the item is disabled with a reason.
  The stub toast is gone.
- **AC-S2-4 [BE]** Given a portal token owning a request with a completed tag
  sheet export, when the portal download route is called, then it streams the PDF;
  not-owned or no-export cases refuse without leaking existence.
- **AC-S2-5 [FE]** Read-only view is usable at 375px and 1280px.

### S3 - design page never dead-ends

- **AC-S3-1 [FE]** Given zero published templates, when marketing opens Design
  Price Tags, then the selected line receives a starter tag built by
  `buildProductBlock` bound to the line's product, on the default tag size, and
  the canvas opens editable.
- **AC-S3-2 [FE]** Given templates still loading or line prices still resolving,
  when the designer looks at the canvas, then the placeholder states the wait
  ("Loading templates...", "Resolving prices...") - never a bare permanent
  "Preparing this line...".
- **AC-S3-3 [FE]** Given the template list request fails, when the page renders,
  then an explicit error state with Retry appears (not a toast that vanishes).
- **AC-S3-4 [FE]** Given a published template exists for the family, when a line
  opens, then behavior is unchanged (clone from family default, `ala_carte`
  fallback, then first template).

### S4 - portal promotions lookup

- **AC-S4-1 [BE]** Given active promotions, when
  `GET /portal/lookups/promotions?q=` is called with a valid portal token, then
  matching active promotions return `{id, name}`; expired/inactive excluded.
- **AC-S4-2 [FE]** Given the portal form, when the salesperson opens the
  promotion dropdown, then real promotions load (searchable, clearable) and the
  chosen `promotion_id` submits; `lookupPromotions` stub is gone.

## Lane B - designer upgrades

### S5 - template save/publish versions

- **AC-S5-1 [BE]** Given a template, when Publish is called, then an immutable
  version row (auto-number, doc snapshot, note, author, timestamp) is created and
  the template's live pointer moves to it. Draft edits after Publish do not change
  the live version.
- **AC-S5-2 [BE]** Given published and never-published templates, when the
  request designer's template source is read, then ONLY published templates (their
  published doc, not their draft) are returned; a never-published template is
  absent.
- **AC-S5-3 [BE]** Given an unpublished action, when Unpublish is called, then
  the template leaves the request designer's list; its draft and versions remain.
- **AC-S5-4 [BE]** Given existing template rows at migration time, when the
  migration runs, then each becomes v1 published (pointer set) - no live outage
  for request design.
- **AC-S5-5 [FE]** Given the template editor, when it renders, then the header
  carries Save (draft), Publish, and a Live/Draft badge; the bottom save bar is
  gone.
- **AC-S5-6 [FE]** Given version history, when the designer opens Versions, then
  versions list newest-first with number, note, author, time; Restore copies that
  version's doc into the draft (confirmation first) without touching the live
  pointer.
- **AC-S5-8 [FE]** Given a past version, when View is clicked, then the canvas
  shows that version's design read-only under a "Viewing vN - read-only" banner
  with Back-to-draft and Restore actions; the unsaved draft is intact after
  returning.
- **AC-S5-7 [T]** pytest covers publish, unpublish, restore, published-only
  resolution, and the v1 migration backfill.

### S6 - editor UX (fullscreen, reflow, guides, per-block preview)

- **AC-S6-1 [FE]** Given the template editor or the request tag designer, when
  Full screen is clicked, then the canvas takes the whole window via the shared
  `FocusShell` (Esc exits), matching the room designer.
- **AC-S6-2 [FE]** Given a text layer, when ANY resize handle is dragged, then
  the box reflows live during the drag and the font size in the saved layer is
  unchanged - corner and edge handles alike.
- **AC-S6-3 [FE]** Given the rulers, when the designer clicks/drags from the TOP
  ruler, then a vertical dotted guide appears at that coordinate; from the LEFT
  ruler, a horizontal one. Guides are draggable and removable (drag back to
  their ruler / delete), session-only - never saved into the doc, never rendered
  on export.
- **AC-S6-4 [FE]** Given a previewable block or group, when it is hovered or
  selected, then an eye affordance on the block itself opens its product/set
  picker; choosing one resolves that block's layers. The toolbar eye is removed.
- **AC-S6-5 [FE]** Given only loose (ungrouped) slot-bound layers, when the tag
  frame's eye is used, then one product choice resolves every loose bound layer
  (whole-tag preview). With nothing bindable the eye is absent.
- **AC-S6-6 [FE]** Given a group of image + texts bound to product slots
  (Ctrl+G), when its eye is used, then that group previews independently of other
  blocks (existing per-block map preserved).

### S7 - barcode

- **AC-S7-1 [BE]** `products.barcode` column exists (nullable, indexed);
  reachable in product responses (asserted - `response_model` trap) and editable
  in the master data product form.
- **AC-S7-2 [BE]** Given the AutoCount canonical product payload carries
  `bar_code`, when ingest runs, then a non-empty incoming value overwrites the
  stored one; an empty/absent incoming value leaves a manually entered barcode
  untouched.
- **AC-S7-3 [FE]** Given the tag editor, when a Barcode layer is inserted, then
  it binds the product's barcode: a valid 13-digit numeric renders EAN-13,
  anything else non-empty renders Code128, empty renders a placeholder in the
  editor and nothing on print/export.
- **AC-S7-6 [FE]** Given a barcode layer, when it renders, then it draws as a
  label plate matching the printed sample: white backing, optional product-code
  strip on top (per-layer toggle), bars, guard-split human-readable digits.
- **AC-S7-4 [E2E]** A tag with a barcode layer previews with a real product's
  barcode and the exported PDF carries the same barcode (render parity - the PDF
  renders through the same frontend print page).
- **AC-S7-5 [BE]** Contract appendix updated: `BarCode` on the canonical product
  wire, documented for the connector.
