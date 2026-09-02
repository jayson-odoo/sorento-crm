# PLAN - Price Tag Feedback R2

Status: Approved 1 Sep 2026 - implementation starting
UAC: `documentation/plans/dealer-kit/price-tag-feedback-r2-acceptance-criteria.md`
Predecessor: `documentation/plans/dealer-kit/PLAN-price-tag-request.md` (shipped, PR #289)

Live feedback batch, 1 Sep 2026. Two lanes in one plan: Lane A fixes what is
broken in live today (attachments lost, read-only view wrong, design page
dead-ends); Lane B upgrades the tag designer (versions, fullscreen, reflow,
guides, per-block preview, barcode). Lane A slices merge alone and first.

## Decisions (grilled 1 Sep)

- D1 one plan, Lane A first, each slice mergeable alone
- D2 attachment timing = the legacy SubmissionForm pattern: buffer pre-draft,
  flush on Save Draft/Submit, immediate upload once the draft exists
- D3 reuse generic `POST /portal/attachments` - whitelist + ownership branch
- D4 CRM shows attachments read-only; upload stays portal-only
- D5 one `PriceTagRequestForm` with a readOnly mode; `RequestDetailView` deleted
- D6 no template -> starter tag from `buildProductBlock` bound to the line's
  product; canvas states explicit (loading / error+retry / starter), never silent
- D7 template versioning = AI-agents pattern: immutable version rows + live
  pointer; publish/unpublish; migration auto-publishes existing rows as v1;
  request design resolves published versions only
- D8 resizing a text box never changes font size, any handle; reflow is live
  during the drag
- D9 ruler guides are session-only visual aids; click/drag from ruler, dotted
  line, draggable, removable; never persisted, never exported
- D10 preview affordance lives ON the block/group (hover/selected eye); loose
  bound layers get a whole-tag eye on the frame; toolbar eye removed
- D11 fullscreen via the existing `FocusShell`/`FocusToggle` on the template
  editor and the request tag designer; no new mechanism
- D12 product block stays fixed 85x58mm on insert; designer rearranges
- D13 live design-page hang root-caused: prod had zero `tag_template` rows and
  the clone effect returns silently on an empty list
- D14 barcode: CRM owns `products.barcode`; AutoCount canonical product wire
  gains `BarCode`; non-empty sync value overwrites, empty leaves manual value;
  manual entry on the product master form; render EAN-13 for valid 13-digit
  numerics else Code128, empty = editor placeholder + nothing on print
- D15 versions list: auto-number + optional note; Restore copies a version's doc
  into the draft; no named labels yet
- D16 a past version is VIEWABLE: View opens that version's doc on the canvas
  read-only (banner "Viewing vN - read-only", Back to draft + Restore from
  there); no editing of history
- D17 BOTH rulers spawn guides: top ruler drops vertical guides, left ruler
  drops horizontal ones
- D18 barcode layer renders as a label plate matching the printed sample: white
  backing, optional product-code strip on top, EAN-13 bars with guard-split
  human-readable digits; code strip toggleable per layer
- D19 portal Download PDF becomes real and lives in a gear dropdown on the
  read-only view
- D20 portal promotions lookup endpoint gets built; the FE stub dies

## Lane A

### S1 - PO attachments end-to-end

Backend (`app/api/v1/public/portal.py`):
- Add `price_tag_request` to the attachment kind space: `_check_kind` stays for
  legacy kinds; the attachments routes get a branch that, for
  `kind == 'price_tag_request'`, checks ownership against
  `PriceTagRequest.contact_id == token.contact_id` (mirrors
  `_require_own_request` in `portal_price_tag.py`) instead of
  `PortalService.get_submission`. `_entity_type_for('price_tag_request')`
  = `'price_tag_request'`; `_kinds_for_entity_type` learns the reverse.
- `portal_price_tag._detail_body`: replace the hardcoded `attachments: []` with
  the same `_list_attachments_for(db, 'price_tag_request', id)` the legacy
  detail uses.
- CRM: `PriceTagRequestResponse.attachments: list[...] = []` (schema), filled in
  `PriceTagRequestService.response_with_resolved_lines` - one implementation
  serves portal + CRM (D49 of the predecessor plan). Route test asserts the
  field (response_model trap).

Frontend portal (`PriceTagRequestForm.tsx`):
- Replace the bespoke `FileDropzone` + dead `pendingFiles` state with the shared
  `AttachmentDropzone` (kind `price_tag_request`), wired exactly like
  `SubmissionForm`: `pendingFiles`/`onPendingFilesChange` while no id,
  `flushPendingFiles(id)` after create in both Save Draft and Submit paths,
  immediate upload + delete once the draft exists.
- Read-only + proof views list attachments via the same components;
  `POCrossCheckViewer` starts receiving real rows.

Frontend CRM (`PriceTagRequestDetail.tsx`): PO Attachments card renders the
response's attachments with the standard preview/download, no upload.

### S2 - read-only parity + real Download PDF

- `PriceTagRequestForm` gains a `readOnly` render mode: same sections, same
  order, inputs swapped in place for values (ADR: View = Edit). Proof statuses
  append the existing proof section under the same layout. Delete
  `RequestDetailView`.
- Gear dropdown (standard menu component) on the read-only header: Download PDF
  enabled when a completed export exists.
- Backend: portal download route for the request's latest completed tag-sheet
  export (ownership via portal token; streams via existing download/storage
  machinery). The FE stub toast dies.

### S3 - design page never dead-ends

`RequestTagDesigner.tsx`:
- Clone effect: when `templates.length === 0` (after load settles), build the
  starter via `buildProductBlock` bound to the line's product on the default tag
  size (`PRODUCT_BLOCK_SIZE`-derived print size), i.e. a synthetic template doc
  fed to `tagForLine`'s pathway - not persisted anywhere.
- Replace the single "Preparing this line..." string with explicit states:
  templates loading, prices resolving, template fetch failed (inline Retry).
- Published-template resolution unchanged otherwise (family -> ala_carte ->
  first).

### S4 - portal promotions lookup

- BE: `GET /portal/lookups/promotions?q=` on the portal price-tag router -
  active promotions only (window current), `{id, name}`, token-gated, same shape
  as other lookups.
- FE: `lookupPromotions` calls it; SearchableSelect stays clearable.

## Lane B

### S5 - template save/publish versions

Schema (dealer_kit):
- `tag_template_version`: id, template_id FK, version_no (unique per template),
  doc JSONB, print_size JSONB, note VARCHAR NULL, created_by, created_at.
- `tag_template.published_version_id` FK NULL.
- Migration: for every existing template, insert v1 from its current
  doc/print_size and point `published_version_id` at it.

Backend routes (tag_templates router):
- `POST /{id}/publish` (snapshot draft -> new version, move pointer, optional
  note), `POST /{id}/unpublish` (pointer -> NULL), `GET /{id}/versions`,
  `GET /{id}/versions/{version_id}` (full doc, for read-only viewing, D16),
  `POST /{id}/versions/{version_id}/restore` (copy doc into draft).
- Published resolution: the list the request designer consumes returns only
  templates with a pointer, serving the PUBLISHED version's doc. The editor
  keeps reading/writing the draft doc. Either a query flag
  (`?published=1`) on the existing list or a sibling route - pick whichever
  keeps `listTemplates` callers honest; the template management list still shows
  drafts with a Live/Draft badge.

Frontend:
- Template editor header: Save (draft PUT, unchanged), Publish (with note
  prompt), Live/Draft badge, Versions sheet (list + View + Restore w/ confirm).
  View swaps the canvas to that version's doc read-only (banner, Back to draft,
  Restore from the banner) - the draft state in memory is untouched.
  `TagCanvasEditor` gets `hideSaveBar` from this host too; the bottom bar dies
  with its last user.
- `RequestTagDesigner`/`TemplatePickDialog` fetch published templates only.

### S6 - editor UX

- Fullscreen: wrap template editor page + request designer in
  `FocusShell`, `FocusToggle` in their headers (labels "template" / "tags").
- Text reflow: `Transformer` gets an `onTransform` live handler for text nodes -
  convert scale into width/height continuously and reset scale so Konva
  re-renders reflowed text at the fixed `fontSize`; `handleTransformEnd` keeps
  owning the commit. Applies to every handle (D8).
- Ruler guides: `CanvasRulers` becomes interactive (D17). Two gestures, both
  Figma/Word style: a single CLICK on a ruler drops a guide at that mm
  instantly; a PRESS-AND-DRAG from the ruler pulls the dashed line out with the
  cursor and lands it on release. Top ruler -> vertical guide, left ruler ->
  horizontal. Guides drag to move, drag back onto their ruler to remove; React
  state only (D9). Guides join `useSnapGuides` targets if
  trivially cheap, else skipped (say which in the PR).
- Per-block preview: previewable blocks (existing `previewableBlocks`) render an
  eye chip when hovered/selected -> that block's picker. Loose bound layers:
  synthesize one whole-tag block (an implicit group over ungrouped bound
  layers) with its eye on the tag frame. Remove the toolbar eye and
  `PreviewBlocksDialog` entry point if nothing else uses it.

### S7 - barcode

Data:
- Migration: `products.barcode VARCHAR NULL` + index. Both response paths
  asserted (response_model trap; check the manual dict builders rule - products
  use schemas, assert in route test).
- `CanonicalProduct.bar_code` + `_product_columns` mapper: overwrite when
  incoming non-empty, keep stored when incoming empty/absent (D14).
- Product master form: Barcode input (optional).
- Contract appendix (AutoCount plan doc): `BarCode` on the product wire, flagged
  for the connector team.

Layer:
- New `TagLayerType 'barcode'` + `BarcodeLayerProps { kind, show_code }` bound
  via slot 'barcode'; InsertField/toolbar entry; Konva renderer (client-side
  generation - jsbarcode or bwip-js, exact-version pinned) rendering EAN-13 for
  valid 13-digit numerics (checksum-checked) else Code128; empty -> dashed
  placeholder in editor, skipped on the print page render.
- Rendered as a LABEL PLATE matching the captain's printed sample (D18): white
  backing with border radius, optional black product-code strip on top
  (`show_code`), bars, guard-split human-readable digits under them.
- Print parity free: the PDF worker renders the same React print page.

## Order and dependencies

S1 -> S2 (read-only view lists attachments) ; S3, S4 independent.
S5 -> S6 is soft (both touch the editor header; S6 rebases on S5's header).
S7 independent; its connector half ships whenever the AutoCount side sends
`BarCode` - manual entry covers the gap from day one.

## Testing seams

- Portal attachment ownership branch: pytest with two contacts' tokens.
- Publish/restore/published-only: pytest on the new routes + resolution.
- Ingest overwrite policy: pytest table - (stored, incoming) -> result.
- Reflow/guides/preview: vitest on the pure helpers (scale->mm conversion,
  guide state, implicit-block synthesis); browser evidence for feel.
- E2E per lane: agent-browser runs per AC-S1-8 / AC-S7-4.

## Out of scope (backlog)

- Named version labels (D15 defers)
- Doc-persisted guides (D9 defers)
- CRM-side attachment upload (D4 defers)
- Barcode on document lines / scanning flows

## Round 3 (captain test on the integration stack, 2 Sep) - decisions D21-D27

- D21 ruler guides: ONE vertical (top ruler) + ONE horizontal (left ruler) guide at a
  time; clicking a ruler places or MOVES that axis's guide. Remove by drag-back to
  the ruler, by selecting the guide + Delete/Backspace, or by the small x at the
  guide's ruler end.
- D22 autosave: request designer autosaves every committed change (debounced ~1s,
  "Saved"/"Saving" indicator in the header; Save stays as a manual flush).
  Template editor autosaves the DRAFT the same way; Publish remains the deliberate
  act.
- D23 barcode value override per layer in the inspector (override wins, Relink
  clears - the text-layer override pattern); lives in the doc only, product master
  stays the source of truth.
- D24 tag size control in the request designer: W x H in mm per line's tag
  (presets = published templates' print sizes + custom), with an "apply to all
  lines" action.
- D25 CRM request detail restructured into tabs: Request / Lines / PO Attachments /
  Proof. Lines rows carry a Design action opening the designer with THAT line
  selected plus a per-line tag status. The standalone Proof card is removed; its
  "Open the designer" moves to the header actions. Font sizes follow system tokens.
- D26 tag templates list: checkbox selection + bulk Delete as a deferred action
  with Undo toast (no confirm dialog).
- D27 sequencing: round 3 lands AFTER the eight round-2 PRs merge (shared files).

### Round-3 defects found on the integration stack (fix on their PR branches)
- portal item picker lists a product twice (lookup_tag_items - diagnose fan-out vs
  duplicate rows)
- request designer canvas collapses at the bottom outside fullscreen (#496 layout)
- a designed tag vanishes on Design -> Arrange -> Design (render, not data; diagnose)

### S8 - guides single-per-axis + autosave (D21, D22)
### S9 - barcode override + tag size control (D23, D24)
### S10 - request detail tabs + per-line Design (D25)
### S11 - tag templates bulk delete, deferred action (D26)
