# PLAN - Price Tag Designer Round 6 (tag size on templates, nudge, clipboard, ghost layers, polygon modes, update template, one CTA, crop, rotation snap)

Status: PLANNED 7 Sep 2026, grill done 7 Sep (calls 1-3 confirmed, call 4 = menu only, G1-G5 confirmed, toolbar trailing = icon buttons, clipboard per user), ready for tickets
UAC: `documentation/plans/dealer-kit/price-tag-r6-acceptance-criteria.md`
Predecessor: `PLAN-price-tag-r5.md` (PR #685)

User test on prod after #712 / #714, 7 Sep 2026, ten asks. One lane, one PR, slices are
commits in the order below. Branch `feat/price-tag-r6` off `origin/main`.

Two editors share one canvas: the template editor (`tag-templates/[id]/page.tsx`) and the
request designer (`price-tag-requests/[id]/design/components/RequestTagDesigner.tsx`), both
mounting `tag-templates/components/TagCanvasEditor.tsx`. Every canvas slice below lands in the
shared editor and so reaches both.

Paths below are relative to `sorento_crm_frontend/` unless prefixed `BE:`.

## S1 - Tag size control on the template editor (D1)

Today the print size is asked once in `TagTemplateDialog.tsx` (create) and never editable
again: the editor page has no size UI, and `tagTemplateService.updateTemplate` sends `{ doc }`
only, so `print_size` never changes even though `BE: TagTemplateUpdate.print_size` accepts it.
The request designer already has the control (`TagSizeControl` in `RequestTagDesigner.tsx`
around line 1210: preset dropdown from published templates + saved sizes, custom W/H committed
on blur, Save as size).

- Lift `TagSizeControl` to `app/(protected)/dealer-kit/components/TagSizeControl.tsx` with
  props `{ width_mm, height_mm, presets, savedSizes?, bounds?, onResize, onResizeAll? }`.
  `onResizeAll` absent hides "Apply to all lines"; `bounds` absent means `MIN_TAG_SIZE_MM`
  floor only (a template has no sheet to fit). The request designer keeps its behaviour
  through the same component.
- Template page: render it in the left rail above LAYERS, the same slot the request designer
  uses. Resize updates `template.doc.width_mm/height_mm` AND `print_size` together (they are
  two copies of one fact; `TagTemplateDialog` already writes both).
- `updateTemplate(id, doc)` sends `{ doc, print_size: { width_mm: doc.width_mm, height_mm:
  doc.height_mm } }`. One helper `printSizeOf(doc)` in `lib/dealer-kit/request-tags.ts`, used
  by both the create path and the update path so they cannot drift.
- Autosave picks the change up as any doc edit does. Publish snapshots `print_size` as it
  already does.
- Layers are NOT moved or scaled on resize (matches `resizeTag`); S4 makes what falls outside
  visible.
- Tests: `TagSizeControl.test.tsx` (lifted, covers preset pick, custom commit on blur/Enter,
  floor clamp, no Apply-to-all when the prop is absent); `tagTemplateService.test.ts` asserts
  the PUT body carries `print_size` equal to the doc's size; `RequestTagDesigner.test.tsx`
  existing size tests still pass through the lifted component.

## S2 - Finer keyboard nudge (D2)

`TagCanvasEditor.tsx:2505` nudges 1 mm per arrow, 0.1 mm with Shift. Inverse of Figma and
too coarse on a 60 mm tag.

- Arrow 0.25 mm, Shift+Arrow 1 mm, Alt/Option+Arrow 0.1 mm. Constants `NUDGE_MM = { base:
  0.25, shift: 1, alt: 0.1 }` next to `CLONE_OFFSET_MM`.
- `InspectorPanel.tsx` X/Y/W/H `NumberInput` step 0.5 -> 0.25 (lines 281-300 and 579-593).
  Rotation step stays 1.
- Shortcut list (the toolbar's keyboard help, if present; else the tooltip on the select tool)
  documents the three steps. No on-canvas explanation.
- Tests: `TagCanvasEditor.nudge.test.tsx` fires ArrowRight plain / Shift / Alt on a selected
  layer and asserts x_mm deltas 0.25 / 1 / 0.1.

## S3 - Clipboard survives switching lines and pages (D3)

`clipboard` is `useState` inside the editor (`TagCanvasEditor.tsx:392`). The request designer
mounts the editor with `key={selectedTag.id}` (line 962), so picking another line remounts the
editor and empties the clipboard: copy on line A, click line B, paste does nothing.

- New `lib/dealer-kit/tag-clipboard.ts`: module-level store `{ get, set, subscribe }` holding
  `{ layers: TagLayer[]; roots: string[]; sourceDocId: string | null } | null`. The editor
  reads it with `useSyncExternalStore`, writes it in `handleCopy` / `handleCut`. Survives
  remount and route change within the SPA; a page reload clears it (acceptable, documented in
  the UAC).
- `handlePaste`: when `sourceDocId` equals the current doc id (same tag or same template),
  offset by `CLONE_OFFSET_MM` as today; when it differs, paste at the copied x/y unchanged so a
  layout copied across lines lands in the same place. The editor gets a `docId` prop (template
  id, or the placed tag id) for the comparison.
- Layers reference assets by id and fonts by family, so a cross-doc paste needs no asset copy.
- Per user by construction (grill 7 Sep): the store is JavaScript memory in the user's own
  browser tab. Nothing is written to the server, localStorage or any shared place, so user A's
  copy can never reach user B's paste; two tabs of the same user do not share it either.
- Tests: `tag-clipboard.test.ts` (set/get/subscribe); `TagCanvasEditor.clipboard.test.tsx`
  unmounts and remounts the editor with a different `docId` and asserts paste inserts the
  copied layers at the original x/y; same `docId` asserts the 5 mm offset.

## S4 - Off-artboard layers ghosted, not hidden (D4)

`resizeTag` only changes W/H; layers keep their positions. The canvas clips drawing to the
artboard (`TagCanvasEditor.tsx:3019`, S9 review S4) and Konva's clip also removes hit
testing, so a layer past the new edge becomes invisible AND unclickable on the canvas. The
user read it as "my price components are gone". They are in the Layers panel.

- Render layers twice in the same order: one pass inside the clip group as today, one pass
  OUTSIDE the clip at `opacity 0.3` with `listening` on and the clipped copy's `listening`
  off. Only layers whose bounds extend past the artboard are drawn in the ghost pass
  (`layerOverflowsArtboard(layer, doc)` in `canvas-geometry.ts`; a fully inside layer is
  drawn once, exactly as now). Selection, drag, transform and the context menu work on the
  ghost. Snap guides ignore ghosts.
- Layers panel: rows whose layer overflows get a small `outside` marker (icon with tooltip
  "Partly outside the tag, it will not print"). No prose on the canvas.
- Print is unchanged (still clipped).
- Tests: `canvas-geometry.test.ts` `layerOverflowsArtboard` (inside / touching / past edge /
  rotated); `TagCanvasEditor.clip.test.tsx` extended: a layer at x > width_mm is rendered in
  the ghost pass, selectable by click, and the LayersPanel row shows the marker.

## S5 - Polygon: select mode vs edit-points mode (D5)

A selected polygon (or a boxed list-only price badge) disables ALL Transformer resize anchors
(`TagCanvasEditor.tsx:3130`, r4b AC-S4-10) because an anchor sits where a corner handle sits.
Result: a polygon cannot be resized by dragging at all, only via Inspector W/H.

- Two modes on the selected polygon/badge, Figma/Illustrator pattern:
  - **Select** (single click): Transformer with the full anchor set + rotate, NO corner or
    edge handles. Points are normalised 0-1 so a box resize scales the shape with no maths
    change.
  - **Edit points** (double-click the shape, or Enter with it selected, or Inspector button
    "Edit points"): anchors off, today's vertex + edge handles on. Esc, Enter, click on empty
    canvas, or selecting anything else leaves the mode. S1 of r5 (Shift lock) keeps working
    inside the mode.
- State: `editingPointsId: string | null`, cleared by the same events that clear
  `cornerHandleLayer` today (derived guard stays: locked / hidden / not a polygon => null).
  `handleLayerDoubleClick` (line 1223) already routes groups into `entered`; add the polygon
  branch there. Inline text edit on double-click is unaffected (text layers are not polygons).
- Cursor: `crosshair` over a vertex handle in edit mode.
- Tests: `TagCanvasEditor.polygon.test.tsx` extended: single click shows anchors and no
  vertex handles; double-click shows vertex handles and no anchors; Esc returns; resizing
  in select mode keeps the normalised points.

## S6 - Update the source template from a request tag (D6)

A `PlacedTag` carries `template_id` (`request-tags.ts:180`). "Save as template" only creates
(`BE: POST /tag-templates/from-tag`, `create_and_publish`). Marketing edits a tag in a request
and wants that design pushed back to the template it came from.

- Toolbar (S7 moves it there) "Template" dropdown, design mode only, disabled with no
  selected tag:
  - **Update "<template name>"** when `template_id` resolves to a template in the published
    list (name from that list). Hidden when the template no longer exists.
  - **Save as new template** (today's dialog).
- Update flow: confirm dialog "Publish this design as v<n+1> of <name>? Every request that
  picks <name> from now on gets this design." with a checkbox **Also apply to the N other
  lines in this request that use <name>** (shown only when N > 0, default ON). Confirm:
  1. `PUT /tag-templates/{id}` with `{ doc: { layers, width_mm, height_mm }, print_size }`
     (existing route; the service's `updateTemplate` from S1).
  2. `POST /tag-templates/{id}/publish` with note `Updated from <doc_number>` (existing).
  3. If the checkbox is on, `applyDesignToAllLines`-style update restricted to sibling tags
     whose `template_id` matches (new pure `applyDesignToSiblings(tags, sourceLineId,
     templateId)` in `request-tags.ts`; the current tag is the source). Undo via the existing
     bulk-apply undo toast, same as "Apply to all lines".
  4. Invalidate the published-templates query so the picker and size presets refresh.
- Template family/name unchanged by Update. Versions sheet on the template page shows the new
  version with the note, so a bad push is reversible with Restore.
- Permission: same `_MANAGE` dependency as create; the button is hidden when the templates
  list request is forbidden (existing behaviour for Save as template).
- Tests: `request-tags.test.ts` `applyDesignToSiblings` (matching template_id updated, other
  template untouched, source unchanged, sizes follow); `RequestTagDesigner.update-template.
  test.tsx` mocks the two calls in order and asserts the sibling apply happens only with the
  checkbox on. BE: no new route; `test_dealer_kit_tag_template_versions.py` already covers
  update + publish + note.

## S7 - One CTA top right, secondary actions in the toolbar (D7)

Request bar today: Back, Design/Arrange, Saved hh:mm, Full screen, Save as template, Save,
Mark proof ready (`RequestTagDesigner.tsx:840-945`). Template page: Versions, Saved, Save,
Publish, Full screen, Back to templates (`tag-templates/[id]/page.tsx:378-422`).

- `CanvasToolbar` gains a `trailing?: ReactNode` slot rendered right-aligned after the zoom
  group, separated by the existing divider. Everything placed in it is rendered with the
  toolbar's own `ToolbarButton` (icon, tooltip with label and shortcut, same size and hover as
  the tool groups on the left) so the right end reads as one more button group, not a row of
  outlined chips (grill 7 Sep). The Template dropdown is a `ToolbarButton` with a caret that
  opens a `DropdownMenu`; Save shows the spinner in place of its icon while saving.
- Request designer trailing: Full screen toggle, Template dropdown (S6), Save. Request bar
  keeps Back, Design/Arrange, `AutosaveIndicator`, and **Mark proof ready** as the only
  button (when `canMarkProofReady`; otherwise the bar's right side holds the indicator only).
- Template page trailing: Versions, Save, Full screen. Page header keeps `AutosaveIndicator`,
  **Publish** as the only button, and `BackToList` (it is navigation, not an action, and the
  standard puts it in the header).
- 375 px: the toolbar already scrolls horizontally (verify); if the trailing slot pushes the
  zoom group off screen, the trailing group collapses into a "..." menu below `md`. No new
  wrap rules in the request bar.
- Tests: `CanvasToolbar.test.tsx` renders `trailing`; `RequestTagDesigner.test.tsx` asserts
  exactly one button in the request bar in designing state and that Save as template / Save
  are found inside the toolbar; template page test likewise for Publish.

## S8 - Image crop (D8)

`ImageLayerProps.cropRect` exists in the type (`tag-template-types.ts:90`) and the BE schema
(`BE: schemas/price_tag.py:282`) but nothing reads it: canvas, print and inspector ignore it.

- Storage: `cropRect = { x, y, width, height }` normalised 0-1 against the SOURCE image.
  Absent = whole image. Crop applies before `fit`, `fit` then places the cropped region in
  the layer box; `maskShape` stays on the box.
- Enter crop mode: context menu **Crop image** on an image layer only (captain call 4,
  grill 7 Sep: no double-click entry). Double-click on an image stays a no-op.
- Crop mode UI (Konva, inside the editor): the full source drawn at 40% opacity in its
  fitted position, the crop window bright with 8 handles clamped to the source bounds,
  dragging inside the window pans the crop. Enter or click outside commits, Esc cancels,
  Transformer anchors hidden meanwhile (same guard as S5). Inspector shows **Reset crop**
  when `cropRect` is set.
- Canvas: `KonvaTagLayer.tsx` `ImageContent` passes Konva `crop={{x, y, width, height}}` in
  source pixels (from the normalised rect times `image.width/height`) and computes the fit
  from the cropped aspect ratio instead of the full image's.
- Print: `TagSheetRenderer.tsx:308` image gets a wrapper `div` with `overflow: hidden` and
  the `<img>` sized `100 / width %` by `100 / height %` offset by `-x / width * 100 %` /
  `-y / height * 100 %`, then the existing `objectFit` rule applies to the wrapper. The
  circle mask stays on the wrapper. One helper `cropStyle(cropRect)` in
  `lib/dealer-kit/image-crop.ts` used by the print path; the Konva path uses
  `cropPixels(cropRect, image)` from the same file.
- Tests: `image-crop.test.ts` (normalised -> pixels, clamp, absent = full); `KonvaTagLayer.
  image.test.tsx` crop prop present when `cropRect` set and fit uses the cropped ratio;
  `TagSheetRenderer.test.tsx` wrapper + offset style; `TagCanvasEditor.crop.test.tsx`
  enter via menu, commit on Enter writes `cropRect`, Esc leaves it untouched, Reset clears.

## S9 - Rotation snap with Shift, live angle, Shift keeps ratio (D9)

Transformer has no `rotationSnaps` (`TagCanvasEditor.tsx:3121`) and `keepRatio={false}`
always.

- `rotationSnaps={[0,15,30,45,60,75,90,...,345]}` (`Array.from({length: 24}, (_, i) => i *
  15)`) and `rotationSnapTolerance={7}` ONLY while Shift is held. Track Shift with a
  `useShiftKey()` hook (window keydown/keyup + blur reset) already needed by S2's modifiers;
  pass `rotationSnaps={shift ? SNAPS : []}`. Konva reads the prop live, so pressing Shift
  mid-rotate starts snapping.
- Angle pill: during a rotate transform (`handleTransform`, line 1666, when the active anchor
  is `rotater`) draw a Konva `Label` 24 px above the rotate handle with the angle to one
  decimal (`12.5°`), integers when snapped (`45°`). Removed on `transformEnd`. Same colour
  as the selection stroke.
- `keepRatio={shift}` for corner anchors so Shift-drag on a corner keeps the aspect ratio
  (side anchors unaffected). Text reflow (`text-reflow.ts`) sees the same width path.
- Tests: `TagCanvasEditor.rotate.test.tsx`: with Shift held the Transformer receives the
  snap list, without it an empty list; keepRatio follows Shift; the angle label text reads
  the node's rotation during transform and is absent after.

## S10 - Right-click on an image opens the layer menu (D10, observed bug)

Screenshot on prod: right-click on a selected image layer showed the EMPTY-canvas menu
(Paste, Select All, Fit to View, Zoom 100%). `handleStageContextMenu` (line 2251) hit-tests
with `hitLayerAt(layers, x, y, entered)` in mm. Reproduce first on the lane with the same
tag (an image layer beside a price badge, unrotated), then fix the actual cause. Candidates,
in the order to check: `pointerMm()` returning null when the event target is the Konva image
node rather than the stage; `hitLayerAt` skipping layers inside a group that is not
`entered`; a z-order tie with the badge. Whatever it is, the fix is in `hitLayerAt` or
`pointerMm`, not a special case in the menu.

- S8's **Crop image** item depends on this menu reaching image layers, so S10 lands before
  S8 in the commit order even though it is numbered last.
- Tests: `TagCanvasEditor.context-menu.test.tsx` right-click on an image layer shows Cut /
  Copy / Crop image; right-click on empty canvas shows Paste / Select All.

## Commit order

S2, S9, S3, S4, S5, S10, S8, S1, S7, S6. The canvas-only slices first (each independently
verifiable in the template editor), then the two that touch page chrome, then S6 which
depends on S1 (`updateTemplate` carrying `print_size`) and S7 (the Template dropdown's home).

## Verification

Vitest per slice as listed. agent-browser run on the lane dev server, sidebar navigation from
`/`, both editors, at 1280 and 375. Evidence PNGs to
`documentation/plans/dealer-kit/seed-assets/verification/r6-*.png`. PDF check for S8 (crop
prints as on screen) and S4 (ghosted layer does NOT print) via the request's Print sheet.

## Out of scope

- Currency on price text slots, mobile inspector, `TagTemplateDocModel` enforcement on save
  (open gaps from r4/r5, unchanged).
- Scaling layers proportionally on tag resize (rejected in discussion: silent design
  mutation, wrong for aspect changes).
- Cross-reload clipboard persistence.
