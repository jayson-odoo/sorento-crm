# PLAN - Price Tag Designer Round 4 (fonts, stale data, inline copy, free-corner shape)

Status: in progress, round 4b committed, browser verification pending; lane `fix/price-tag-r4` cut off `origin/main` dbba826bf on 5 Sep 2026
UAC: `documentation/plans/dealer-kit/price-tag-r4-acceptance-criteria.md`
Predecessor: `documentation/plans/_archive/dealer-kit/PLAN-price-tag-ux-r3.md` (shipped #625)

User test on live, 5 Sep 2026, after #625. Four findings, one lane, one PR, four slices.

## What was measured (origin/main dbba826bf)

- **Fonts never load.** `asset_service.font_assets` (`app/services/dealer_kit/asset_service.py:322-346`)
  returns a signed CDN URL per font. New uploads go to R2 (`STORAGE_DEFAULT_PROVIDER=r2`); a real
  signed URL on `pub-*.r2.dev` answers `200` with NO `Access-Control-Allow-Origin` (probed 5 Sep).
  `FontFace.load()` needs CORS, rejects, and `lib/dealer-kit/fonts.ts:96-107` swallows the
  rejection, so Konva and the print page both fall back to the system sans. `app/services/
  media_proxy_service.py` documents the same host behaviour and proxies bytes for the chat
  preview: that is the precedent. Family naming is correct end to end (`useTagBindings.ts:219-227`,
  `KonvaTagLayer.tsx:225`); the dialog prefills the family from the filename
  (`FontUploadDialog.tsx:50-54`), which is why one upload is "centurygothic" and the other
  "Century Gothic Bold".
- **Barcode "missing" is stale line data.** `RequestTagDesigner.tsx:232-245` calls
  `resolveRequestLines` once on mount; `boundData` (`:372-376`) is built from that snapshot.
  Editing the product's barcode in another tab and returning leaves every layer resolving
  against the old row, so a new or relinked Barcode layer shows the "No barcode on the product"
  placeholder (`InspectorPanel.tsx:1077`) until a reload. The backend plumbing is correct
  (`tag_data_service.py:343`, `schemas/price_tag.py:757`).
- **Inline editor shows the raw token.** `contentFor` (`TagCanvasEditor.tsx:2252-2263`) returns
  `props.text` verbatim for an unbound layer, so a layer whose text is `{{product.code}}` opens
  the `InlineTextEditor` on the token, while the canvas resolves it through `layerText` ->
  `renderMergeFields` (`product-block.ts:231-241`). No test covers a token layer.
- **Shapes are rect / rounded_rect / ellipse / line** (`tag-template-types.ts:41`), drawn in
  `KonvaTagLayer.tsx:380-435` and `TagSheetRenderer.tsx:164`. The Transformer resizes the box
  only; nothing lets a corner move on its own. The reference tag's price callout is a
  four-sided shape with a slanted left edge.

## S1 - Serve font bytes same-origin (BE + FE)

- New public route `GET /api/v1/public/dealer-kit/fonts/{asset_id}` in
  `app/api/v1/public/` (the print page is unauthenticated, driven by the PDF worker, and needs
  the same bytes). Looks up `dealer_kit.asset` with `kind='font'` only (any other kind or
  unknown id -> 404), reads the bytes through the storage router for the row's provider, and
  returns them with the font `Content-Type` (reuse `mime_for_upload`), `Cache-Control:
  public, max-age=86400`, and the file name. No auth: ids are UUIDs, font bytes are brand
  assets, and the route cannot enumerate. Stream, do not buffer into memory if the storage
  backend offers a streaming read; otherwise read once (fonts are < 5 MB, the upload cap
  already bounds this).
- `font_assets()` returns `url` as that PATH (`/api/v1/public/dealer-kit/fonts/<id>`), no CDN
  signing. Both consumers turn the path into an absolute URL with the api base helper each
  already uses: the editor (`useTagBindings.ts:196-201` via the FE asset listing - the FE builds
  the path from `asset.id`, it does not need the backend field) and the print page
  (`page.tsx:90` has `apiBase()`; prefix `body.fonts[].url` when it starts with `/`).
- `fonts.ts`: `ensureFontsLoaded` returns `{ failed: string[] }` (families whose face rejected)
  instead of swallowing silently; `useTagBindings` toasts once per family: "Font <family>
  could not be loaded". The print page ignores the return (a PDF with fallback beats no PDF).
- Tests (test-first): pytest route (font -> 200 + `font/ttf`, image asset -> 404, unknown ->
  404, cache header); vitest `fonts.test.ts` (rejecting face is reported in `failed`, resolving
  face is added once, idempotent); vitest for the path builder.

## S2 - Re-resolve line data when the designer regains focus (FE)

- `RequestTagDesigner.tsx`: on `window` `focus` and on `document` `visibilitychange` ->
  `visible`, call a silent variant of `loadPrices` that keeps `pricesStatus` as is and only
  swaps `resolvedRows` on success (no loading flash, no error state on a failed background
  refresh). Debounce with a 1 s guard so focus + visibilitychange do not double-fire.
- Test: vitest - mount, fire `focus`, assert `resolveRequestLines` called twice and the canvas
  never re-enters the loading state.

## S3 - Inline editor shows the resolved value for a sole-token layer (FE)

- `merge-fields.ts`: `soleMergeField(text)` -> the single `{{path}}` token when the trimmed
  text is exactly one token, else `null`.
- `TagCanvasEditor.tsx`: when the editing layer is unbound, its content is a sole token, and
  `renderMergeFields(content, dataOf(layer), 'print')` yields a non-empty value, pass that
  value to `InlineTextEditor` with `readOnly`. Otherwise unchanged.
- `InlineTextEditor.tsx`: `readOnly` -> textarea `readOnly`, all text selected on open so
  Ctrl/Cmd+C copies it, Enter / Escape / blur close WITHOUT commit. Inspector Content box
  unchanged (still the raw template, still editable).
- Tests: `InlineTextEditor.test.tsx` readOnly never calls `onCommit`; `TagCanvasEditor.
  inline-edit.test.tsx` token layer + `boundData` opens on the resolved code, and a mixed text
  ("Code {{product.code}}") still opens raw.

## S4 - Polygon shape with draggable corners and edges (FE + doc schema)

- `ShapeType` gains `'polygon'`. `ShapeLayerProps` gains `points?: {x: number; y: number}[]`,
  each in [0, 1] relative to the layer box (so the Transformer's resize still scales the
  shape and old docs need no migration). Missing `points` on a polygon = the four corners.
  `cornerRadius` applies to every vertex, clamped per vertex to half the shorter adjacent edge.
- New pure helper `lib/dealer-kit/polygon-path.ts`: `roundedPolygonPath(points_px, radius_px)`
  -> SVG path `d`; `movePoint(points, i, dx, dy)` and `moveEdge(points, i, dx, dy)` (edge i =
  vertex i to i+1) both clamp to [0, 1].
- Konva: `case 'polygon'` renders react-konva `Path` with `data` from the helper (one path
  builder for both renderers). Print: `renderShapeLayer` polygon -> inline `<svg viewBox="0 0
  w h">` + `<path d>` at the layer's mm size, fill/stroke from props.
- Editing: double-click a polygon layer -> `editingShapeId`. The editor draws, in stage
  space, a circle handle on every vertex and a small square handle on every edge midpoint;
  dragging a vertex calls `movePoint`, dragging a midpoint calls `moveEdge`; commit to the
  layer props on drag end (one history entry per drag). While editing, the Transformer is
  detached from that layer; Escape or click on empty canvas exits. Inspector shape select
  lists "Polygon (free corners)"; switching a rect / rounded rect to polygon seeds the four
  corners; switching away drops `points`. Toolbar "Add Shape" behaviour unchanged.
- Backend, added during implementation: `ShapeLayerPropsDoc` in `app/schemas/price_tag.py`
  is `extra='forbid'` and mirrors `tag-template-types.ts`, so it gains `'polygon'` and an
  optional `points`. Nothing in the request path validates a doc through it today (every
  `doc` field is a plain `dict`) - it is the type check the SEEDED templates are held to -
  but leaving it behind would make the mirror a lie and would reject the first seeded layout
  that used a polygon. No migration, no route change.
- Tests: `polygon-path.test.ts` (square r=0 -> M/L/L/L/Z, radius clamp, clamps on move);
  `TagCanvasEditor.polygon.test.tsx` (double-click enters edit mode, vertex drag end writes
  the new normalized point, Escape exits); `TagSheetRenderer` renders an `<svg><path>` for a
  polygon layer; `test_tag_template_seed_docs.py` (a polygon doc with and without `points`
  validates, an unknown shape still does not).

## Verification

Agent stack FE :3080 / BE :8080 from this worktree, booted by the main session for the test
only. agent-browser via the sidebar: Dealer Kit -> Price Tag Requests -> open PT-202609-0001 ->
Design. Evidence per UAC.

## S5 - Barcode value can be cleared and typed over (FE)

Measured: `InspectorPanel.tsx` barcode input writes `onUpdate({ text_override: e.target.value
|| null })`, so deleting the text sets the override to null, which MEANS "follow the product"
(`resolveBarcodeValue`, `product-block.ts:142-147`), and the product barcode snaps straight
back. The text layer's Content box (`:452-455`) writes the raw value and does not have this
problem. User, 5 Sep: "I should be able to delete and write whatever I want; if I want to
relink I should just click the Relink button we already have."

- Barcode input writes `text_override: e.target.value` (empty string is an override that draws
  no barcode; Relink is the only way back to the product value). `KonvaTagLayer` and the print
  renderer treat an empty override as "nothing to draw" (no bars, no digits, the plate and the
  code strip still follow `show_code`), never as "fall back to the product".
- Test: `InspectorPanel.test.tsx` - clearing the box calls `onUpdate` with `''` and the Relink
  button stays; `KonvaTagLayer.barcode.test.tsx` - empty override draws no bars.

## Round 4b - captain's test on :3080 (5 Sep, after the first six commits)

Findings, all on the same lane:

- **S3 miss.** Double-click on the seeded product-code layer still opens `{{product.code}}`.
  The layer has a `slot_binding` AND a `text_override` holding the token (D57: a bound layer
  typed over with a merge field keeps following the product). `editingResolvedValue`
  (`TagCanvasEditor.tsx:2540`) returns null for any bound layer, so the rule never fires.
  Fix: drop the `slot_binding` exclusion; the rule is "content is a sole token that resolves",
  for any layer. Trim the resolved value (review nit 10).
- **S4 UX.** The user selected Polygon and expected to drag the corners straight away; nothing
  showed because handles were behind double-click. Revised design: a polygon layer that is the
  SOLE selection shows its corner and edge handles immediately; the Transformer keeps only the
  rotation anchor for it (no box anchors, they would sit on top of the corner handles). Corners
  are no longer clamped to the box: a drag past the box grows the box. On drag end, convert the
  points to local mm, take the bounding box, shift the layer's x/y along its rotated axes,
  set width/height, and renormalise the points to [0, 1]. W/H inputs still scale the shape.
  Double-click is no longer needed (keep it harmless). Label is "Polygon", not "Polygon (free
  corners)". Edge handle and shape must stop together (review item 3 becomes moot once the
  clamp is gone, but the handle must still snap to the recomputed midpoint on drag end).
- **S6 price badge box.** "List price only" ignores Box Fill because `priceBadgeParts` sets
  `boxed: false` for that variant (D26 kept the box for promo). The user wants the badge itself
  to be the white callout instead of a shape behind it. Add `showBox?: boolean` to
  `PriceBadgeLayerProps` (absent = false, so every saved list-only badge prints unchanged);
  Inspector shows a "Box" checkbox for the list-only variant; promo stays always boxed.
  `priceBadgeParts` takes `showBox` into account for `boxed`. And the box takes the same
  optional `points` as a polygon, drawn with `roundedPolygonPath` in both renderers, with the
  same on-selection handles as S4, so the slanted callout is the badge itself. Text stays
  centred in the layer box.
  Narrowed during implementation, and `priceBadgeParts` now says which of the two it is with a
  `polygonBox` field: the CORNERS belong to the list-only callout, whose box is the whole
  layer box in millimetres. The promotional block's box is only the part of the layer left
  under the struck price - a height the print page never states, because it lays that block
  out with flex - so it keeps the rounded rectangle it has always had in both renderers, and
  shows no corner handles. That is what AC-S6-3 asks for; drawing its box from a path would
  have meant re-laying the promo badge out in fixed proportions and changing what promo
  prints. One consequence worth knowing: a promo badge that had Box ticked while it was
  list-only and then loses its offer keeps the box on the list-price fallback, because the
  flag is read in the shared fallback branch rather than gated on the variant.
- Review should-fix 1 and 2 (relative font path in the browser; freeze the read-only decision
  per edit session) and nits 4-9 land in the same pass.
- **S6b price badge typography.** The badge's figure has no text controls; a text layer has
  Font Family (+ Upload font), Font Size, B/I/U/S, Font Weight, Colour, Align, Line Height,
  Letter Spacing. `PriceBadgeLayerProps` gains the same optional typography fields as
  `TextLayerProps` (`fontFamily, fontSize, fontWeight, italic, underline, strikethrough,
  align, lineHeight, letterSpacing`); absent = today's look, so saved badges print unchanged.
  The Inspector's typography block is extracted from the text section into one shared
  component used by both the text and the price badge sections. Both renderers apply the
  fields to the badge's figure; the struck LP line, SP and NETT parts keep their proportion to
  the figure exactly as they scale today. Text Colour stays the badge's colour field.

## S7 - Rail split survives a line change (GitHub #676)

Reported 5 Sep from the sorento-crm-3d session: drag the TAG SIZE / LAYERS divider in the
request designer's left rail, click another line, the split snaps back.

Measured: `RequestTagDesigner.tsx:925` mounts `<TagCanvasEditor key={selectedTag.id}>`, so a
line change remounts the editor. The split IS persisted already: `handleRailResize`
(`TagCanvasEditor.tsx:1989-1998`) writes `railSplit` through `persistPanelLayout` ->
`writePanelLayout` (localStorage `dealer-kit.canvas-panels.v1`) on every drag, and the hydrate
effect (`:1907-1913`) reads it back after mount. But `react-resizable-panels` reads a panel's
`defaultSize` ONCE at mount, and at first render `panelGroupSize.height` is 0 so `railPercent`
is computed against the 600 fallback with the DEFAULT layout; when the stored value and the
real group height arrive one render later, nothing tells the panel to move (the collapsed flags
already get the same imperative treatment, `:1911-1912`). So the value round-trips through
storage and is never applied. No state lifting needed.

Fix: hold a ref on the rail `Panel`; after hydration AND once `panelGroupSize.height > 0`,
call `railPanelRef.current?.resize(percentFromStored)` once (guard with a ref so a later
ResizeObserver tick does not fight the user). Test in `TagCanvasEditor` panels test: stored
`railSplit` in localStorage -> after mount the rail panel receives `resize(<percent>)`;
remount with a new `key` -> same. Close #676 in the PR body.

## Round 4d - three defects from the run-3 test (5 Sep, on :3080)

- **Text prints in a serif, and it is not a Century Gothic problem.** Measured on the print
  page for download `a3dddfb3` (page version 5) before any change: the `code` layer, which
  names `Century Gothic`, embedded `/AAAAAA+CenturyGothic` in the PDF and drew correctly. What
  printed serif was every layer naming `DM Sans` - the spec lines and the other two tags' code
  layers - which embedded `/BAAAAA+Times-Roman`. `DM Sans` is the family `defaultTextProps`
  gives every new text layer and the first entry in `STATIC_FONT_OPTIONS`, and NOTHING loaded
  it: `document.fonts` on the print page listed Inter, keenicons, Geist, Bebas Neue, Jost and
  the two uploaded Century Gothic faces, and no DM Sans. Chromium answers an unmatched family
  with its standard font, which is a serif, so both surfaces drew the app's own default font as
  Times. Fix: `DM Sans` joins `TAG_FONT_STYLESHEET` and `SEED_FONT_FAMILIES`, the one place both
  the editor and the print page take their stand-in faces from, and `ensureSeedFontsLoaded`
  waits for the 700 weight as well as the 400 (a CSS-connected face loads per weight, on
  demand, and the print page raises its ready flag the moment that wait resolves). Re-rendered:
  no `Times-Roman` in the PDF at all.
- **375px scrolled the root.** `documentElement.scrollWidth` was 898 at 375px while
  `body.scrollWidth` was 375, and nothing unclipped reached past 376. The 898 was the right
  edge of the LAST toolbar button's `sr-only` label: `sr-only` is `position: absolute`, an
  absolutely positioned box is clipped by an ancestor's overflow only when that ancestor is in
  its containing-block chain, and the r4c `overflow-x-auto` row is `position: static`. So the
  labels laid out against the initial containing block and stretched the document while the
  toolbar itself sat still. Proved in the page: setting that row to `position: relative` took
  `scrollWidth` from 898 to 375 with nothing else touched. Fix: the row is `relative`.
- **Escape mid-drag committed the half-drag.** Konva delivers a `dragend` for a node destroyed
  mid-drag, and Escape destroys the corner handles by deselecting, so `handlePolygonDragEnd`
  ran on a drag the user had just abandoned and refitted the box around it (W 33.2 -> 52.54,
  autosaved). The r4c effect that clears `polygonPreview` when `cornerHandleLayer` goes null
  runs after that, too late. Fix: `polygonDragRef` carries a `cancelled` flag, the Escape
  handler sets it before deselecting, and `handlePolygonDragEnd` checks it first - so the
  release that follows, whenever it arrives, writes nothing. The tester's companion report that
  Undo was greyed out afterwards did NOT reproduce: on the failing build the commit pushed a
  history entry and the toolbar Undo both enabled and reverted it.
