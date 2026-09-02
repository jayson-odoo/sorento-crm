# PLAN - Price Tag Feedback R2

Status: Round 2 (S1-S7) in 8 reviewed PRs awaiting merge; round 3 (S8-S11) built,
reviewed and merged into integration/price-tag-r2 for captain testing (2 Sep).
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

Delivered. What shipped:

**Guides (AC-S8-1/2).** `placeOrMoveGuide` is the single function both the ruler
click and the drag-spawn gesture go through, so an axis can only ever hold one
guide - a second click on the same ruler MOVES it. Three removal paths: drag
back onto the spawning ruler, select + Delete/Backspace, or the x chip drawn at
the guide's own ruler position. A guide and a layer are never selected at once
(review B4): selecting either clears the other, and the Delete handler asks
about the guide FIRST, so what the key removes is always what was clicked last.
Guides stay session-only React state - never in the doc, never exported (D9).

**Autosave (AC-S8-3/4).** New `hooks/useAutosave.ts`: ~1s debounce, status +
savedAt + flush + retry, and saves are SERIALISED - each one chains onto
whatever is in flight, because two overlapping PUTs of the same document can
land in either order and the loser is what the server keeps. `AutosaveIndicator`
reads it next to each host's manual Save button. Both the request tag designer
and the template editor use it.

The autosave and the manual button are two different acts with two different
contracts (review B2/B3): the autosave path is SILENT and rethrows, so the
indicator is its whole report and a failure reaches it; the manual path keeps
its toast and rethrows, so Mark proof ready / Print sheet abort rather than
transitioning off a design the server never received. Both flush before they
act (review S4), so neither can race the debounce.

Two changes are deliberately NOT autosaved: the initial document as loaded, and
the starter/template clone a line gets when it has no tag yet (review S3) -
that is the page deciding what to draw, not the user deciding anything, so
opening a request with undesigned lines, or clicking down the rail to look at
them, now persists nothing.

Leaving the page flushes (review S1/S2). An in-app route change - the back
link, the sidebar, the browser's Back - unmounts the host, so the effect
cleanup is where the last edit gets its chance; `pagehide` covers the refreshes
and closes React never hears about, and replaces `beforeunload` (too early, and
skipped outright when mobile Safari discards a backgrounded tab). The teardown
request alone goes out `keepalive: true` so it outlives the document - not
every request, because a keepalive body is capped at 64KB and a busy tag sheet
exceeds it.

**`page.draft_doc` (captain ruling 2 Sep, review B1).** Autosave must NOT create
`page_version` rows: routed through the manual Save endpoint, a minute of
nudging a layer wrote sixty immutable versions and buried the deliberate saves.
Migration 456 adds `dealer_kit.page.draft_doc` JSONB NULL (chains on
`455_products_barcode`, replay-guarded like 453/454, hand-applied once on the
shared dev DB with `alembic_version` left where it was - the documented drift).
The split mirrors S5's template draft/live model:

- `PUT /{id}/design/draft` overwrites `draft_doc` in place. No version, ever.
- `PUT /{id}/design` (manual Save) snapshots the document into one new
  `page_version` and clears `draft_doc`.
- The `proof_ready` transition promotes an unsaved draft the same way, because
  the proof renders from VERSIONS and the detail page's header can transition a
  request whose designer tab still holds one.
- `GET /{id}/design` answers the draft when present, else the latest version,
  and says which in `source` - reopening on the version would silently discard
  everything since the last Save.
- Both write routes carry `_PROCESS` + `validate_designable` (S10's guard), so
  a stale tab cannot autosave over an approved or void request either.
- Export and proof rendering are untouched: they read versions only.

NOT built, and why: a `draft_updated_at` / "unsaved changes" cue on the detail
page. Nothing asks for one today and the indicator already says it live in the
designer; the trigger that would justify it is a second person needing to see
that a request has work in progress before opening it.

### S9 - barcode override + tag size control (D23, D24)
### S10 - request detail tabs + per-line Design (D25)
### S11 - tag templates bulk delete, deferred action (D26)

Shipped on `price-tag-r3-s11` (PR #511), review round 2 Sep.

Frontend (`TagTemplatesList.tsx`):
- Checkbox selection (`buildSelectColumn`) + a Delete action in
  `DataGridListToolbar`'s bulk strip. No dialog: ONE `useDeferredAction` parked
  on a client-generated batch token, with the countdown in a toast naming the
  COUNT ("Deleting 12 templates"), and every selected row dimmed for the window
  via the new `dimEntityIds` (store + `DataGrid`'s `rowPending`). The count says
  how many, the dimming says which - which is what the old "a countdown can only
  name one record" objection to deferring a bulk action was missing.
- One parked action per batch, never one per row (`useDeferredBulkAction`'s
  shape): the server refuses or applies the whole selection together, and a
  per-row action cannot express that.
- The PER-ROW Delete moved to the same model (`useDeferredRowAction` over
  `tag_template.delete`); `ConfirmDeleteDialog` and the now-unused
  `deleteTemplate` service call left the file.
- Ids and the outcome noun are frozen at the click, because the selection is
  cleared immediately afterwards.

Backend:
- `tag_template_service.bulk_delete` / `delete_template`: all-or-nothing over the
  batch, one 404 with the SAME sentence for a missing id and for another
  company's (no existence oracle), the company predicate spliced on EXPLICITLY
  rather than left to the `do_orm_execute` listener alone. `DELETE
  /tag-templates/{id}` now calls the same service method, so immediate and
  deferred cannot drift. One audit row per deleted template (the templates
  themselves are gone afterwards, and the action row names the CLICK) plus an
  INFO log naming ids, names and the requester.
- `record_actions`: `tag_template.delete` + `tag_template.bulk_delete`, both
  `dealer_kit.tag_templates.manage`, destructive window.

Executor company scope (the review round's blocker, and NOT specific to this
slice):
- A parked action was executed on whatever session got to it first - the
  scheduler sweep runs `set_company_scope(db, None)` (every company, because a
  tick has no principal), and a lazy commit runs inside somebody else's request.
  The permission check at the click is a SLUG check and never was a company
  check, so a company-A user could park an action naming a company-B record and
  the sweep would carry it out ten seconds later. Every record action shared
  this, not just the batch.
- Fix: `dispatch` stores the requester's resolved scope on the parked row under
  a reserved payload key (`__company_scope`), and `_execute` puts it back around
  `action.execute`. A row parked before the key existed commits UNSET (0 rows),
  never `None` - fail-closed, the same rule a session that never resolved a scope
  gets. The key is stripped before any handler sees the payload; nothing renders
  the payload, so this needed no migration.
