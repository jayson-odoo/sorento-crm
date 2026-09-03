# PLAN - Price Tag Designer UX Round 3

Status: Approved 3 Sep 2026 (lavish + grill, mockups approved) - implementation starting
UAC: `documentation/plans/dealer-kit/price-tag-ux-r3-acceptance-criteria.md`
Predecessor: `documentation/plans/dealer-kit/PLAN-price-tag-feedback-r2.md` (shipped #549)

User test on live 3 Sep 2026 after #549. Seven UX asks on the request designer:
resizable/collapsible panels, Google-Slides-style inline text editing with
B/I/U/S shortcuts, a Figma-style colour picker, save-as-size, save-as-template,
apply-design-to-all-lines, and a dynamic imposition. Decisions D1-D9 are in the
UAC. One lane, one PR, six slices.

All line refs are `origin/main` at 340fbc1cb.

## What exists (measured)

- Panels: `TagCanvasEditor.tsx:2131` left `w-52` (holds `leftRail` = LinesRail +
  TagSizeControl, then LayersPanel `flex-1`), `:2554` right `w-60`. Fixed
  Tailwind, hidden below md/lg. `components/ui/resizable.tsx` wraps
  `react-resizable-panels` (already a dep) - unused by this editor.
- Text: `TextLayerProps` (`lib/dealer-kit/tag-template-types.ts:101-111`) has
  `fontWeight` only. Inspector textarea `InspectorPanel.tsx:472`. Keyboard handler
  `TagCanvasEditor.tsx:1810-1919` with an `isInput` guard. Double-click on a
  group enters it (`handleLayerDoubleClick:1088`); on a text layer nothing.
  Print: `TagSheetRenderer.tsx:127-157` maps props to CSS 1:1.
- Colour: `ColorPicker.tsx` = native `<input type=color>` + 12 `BRAND_SWATCHES`.
- Tag size: `tagSizePresets(templates)` (`request-tags.ts:208`) derives from
  published templates + starter; no table. "Apply to all lines" = `resizeAllTags`
  + `doc.default_tag_size`.
- Templates: `POST /dealer-kit/tag-templates` accepts full `doc` + `print_size`
  (`schemas/price_tag.py:418`); publish is a separate route
  (`tag_templates.py:215`). `PlacedTag.template_id` per line exists.
- Imposition: `IMPOSITION_PRESETS` (`tag-template-types.ts:297-311`) has no
  cols/rows; `impositionSlots` (`request-tags.ts:324-365`) hardcodes 1x3 / 2x2 /
  1. Slot size = largest tag (`autoArrange:430`).
- Deferred-action Undo toast pattern: S11 bulk delete (#511).

## S1 - Panels collapse + resize (FE only)

`TagCanvasEditor.tsx` layout becomes a horizontal `ResizablePanelGroup`:
`[left panel][handle][canvas][handle][right panel]`. Left panel is itself a
vertical group `[rail][handle][layers]` when `leftRail` is present (request
designer); the template editor has no rail so it is just Layers.

- New `lib/dealer-kit/canvas-panels.ts`: `PanelLayout` type `{left: number,
  right: number, railSplit: number, leftCollapsed: boolean, rightCollapsed:
  boolean}`, `DEFAULT_PANEL_LAYOUT`, `readPanelLayout()` / `writePanelLayout()`
  (localStorage `dealer-kit.canvas-panels.v1`, try/catch, clamp to min/max).
  `react-resizable-panels` sizes are percentages; store pixels and convert
  against the group's width on mount (`onLayout` gives percentages back).
- Collapse: `Panel collapsible collapsedSize={0} minSize=...` with `imperative
  ref.collapse()/expand()`; a 24px strip with a chevron renders when collapsed
  (outside the panel so it stays clickable at size 0).
- Both panels stay `hidden` below md/lg exactly as today (AC-S1-7).
- Reduced motion: no transition class on the panels; the primitive has none.
- Konva stage refit: the editor already listens for container resize (the fit
  logic behind Ctrl+0); call it from `onLayout`.

## S2 - Inline text edit + B/I/U/S (FE only)

Types: add `italic?: boolean; underline?: boolean; strikethrough?: boolean` to
`TextLayerProps`; `defaultTextProps()` sets none (absent = false, so old docs
load unchanged).

Pure helpers, `lib/dealer-kit/text-format.ts` (test-first):
- `toggleBold(weight) => weight >= 600 ? 400 : 700`
- `toggleFlag(layers, ids, flag)`: target = !all-true, apply to every id.

Canvas: `KonvaTagLayer.tsx` Konva `Text` gets `fontStyle` =
`[italic && 'italic', weight >= 600 && 'bold'].filter(Boolean).join(' ') ||
'normal'` (Konva only knows bold/italic in fontStyle; the numeric weight is kept
for `fontFamily` variants that exist) and `textDecoration` = `underline` /
`line-through` / both.

Print: `TagSheetRenderer.tsx` `renderTextLayer` adds `fontStyle: italic ?
'italic' : 'normal'` and `textDecoration` (same join).

Inline editor: new `InlineTextEditor.tsx` in `tag-templates/components/`.
Double-click on a text layer (extend `handleLayerDoubleClick`: text -> edit,
group -> existing behaviour) sets `editingLayerId`. The component renders a
`<textarea>` absolutely positioned over the stage container at
`node.getAbsolutePosition()` x stage scale, width/height from the node, font
props copied, rotation via CSS transform. Enter inserts newline; Esc /
Cmd+Enter / blur commit via the same handler the inspector textarea uses
(`text_override` when slot-bound, else `props.text`). While
`editingLayerId` is set the global keydown handler returns early for everything
except the four format shortcuts (the `isInput` guard already covers most of
it; add the explicit early return for safety).

Shortcuts in the existing handler: `Cmd/Ctrl+B`, `+I`, `+U`, `+Shift+X`, applied
to `selectedIds` filtered to text layers, one history entry.

Inspector: `TextInspector` gains a `ToggleGroup` (B I U S) beside Font Size.

## S3 - Colour picker (FE only)

Replace `ColorPicker.tsx` internals; keep its props so the five call sites in
`InspectorPanel.tsx` are untouched.

- `lib/dealer-kit/colour.ts` (test-first): `hexToHsv`, `hsvToHex`,
  `normaliseHex` (3 -> 6 digits, upper), `tagColours(layers): string[]`
  (collects `props.color`, `props.fill`, `props.stroke`, badge colours; dedupe;
  order by count desc; cap 16).
- Picker UI: SV square (div with two gradients, pointer drag via
  `setPointerCapture`), hue bar, hex input, eyedropper button rendered only when
  `'EyeDropper' in window`, "This tag" row, Brand row. No dependency added; the
  square is ~60 lines. Popover = existing Radix `Popover`.
- `TagCanvasEditor` passes `layers` down so the picker can compute "This tag";
  `InspectorPanel` already receives them.

## S4 - Tag size presets + Save as template (BE + FE)

Backend:
- Model `TagSizePreset(Base, CompanyScopedMixin)` in `models/dealer_kit.py`,
  table `dealer_kit.tag_size_preset`, unique `(company_id, name)`.
- Migration `460_tag_size_preset` (chain onto the lane's head after merging
  main; run `scripts/alembic-reparent.sh` at the pre-PR gate).
- Schemas `TagSizePresetCreate/Update/Response` (`schemas/price_tag.py`);
  width/height `ge=10`.
- Router `api/v1/dealer_kit/tag_sizes.py` mounted in `dealer_kit/__init__.py`;
  `_VIEW` / `_MANAGE` = the tag_templates dependencies (D9). Name clash -> 409
  `DUPLICATE_NAME`.
- `POST /dealer-kit/tag-templates/from-tag` in `tag_templates.py`, declared
  before `/{template_id}`: create + publish v1 in one transaction (reuse the
  publish route's body as a service function `tag_template_service.publish`).
- Tests: `tests/test_tag_size_presets.py`, `tests/test_tag_template_from_tag.py`
  (Postgres fixture, zzt_ scratch, seed own rows).

Frontend:
- `services/tagSizeService.ts` (list/create/update/delete) + hooks.
- `TagSizeControl`: dropdown groups (SearchableSelect `groups`) - Template sizes
  / Saved sizes / Custom. "Save as size" button visible when Custom; name
  dialog; on save select it. Saved size x -> deferred delete + Undo toast.
- `/dealer-kit/tag-sizes` page: `TagSizesList.tsx` (DataGrid, fixed layout,
  resizable columns, ListSearchInput, row `...` menu for Edit/Delete),
  `TagSizeDialog.tsx` create/edit modal.
  Menu entry in `config/menu.config.tsx` after Tag Templates, permission
  `dealer_kit.page.view` (same as its siblings).
- "Save as template" in the designer header (next to Save): dialog name +
  family (family options = the existing family list used by
  `TagTemplateDialog`). Payload built by `templateFromTag(tag)` in
  `request-tags.ts` (test-first): strips `text_override`, remaps ids
  (`cloneLayersWithFreshIds` exists for duplicate; reuse), `print_size` from
  tag w/h. On success: toast with Open action; invalidate the published
  templates query so the picker refreshes.

## S5 - Apply design / template to all lines (FE only)

- `request-tags.ts` `applyDesignToAllLines(tags, lines, sourceLineId, newId)`:
  for each line != source, `structuredClone(source.layers)` with fresh ids,
  `bindTemplateLayers(layers, bindingForLine(line))` (rebinding keeps
  `text_override` as-is, which is D3 verbatim), size + `template_id` copied,
  existing `pinned`/positions preserved from the previous tag if any. Lines with
  no tag yet get one (AC-S5-5).
- `RequestTagDesigner`: rail header button; before applying, snapshot `tags`
  and push one undo entry; toast "Applied to N lines" with Undo restoring the
  snapshot (same helper the bulk-delete deferred action uses for the toast).
- `TemplatePickDialog`: "Apply to all lines" checkbox; when on, `chooseTemplate`
  runs for every line with the same undo snapshot + toast. The existing
  edited-confirm path (`replaceAsk` + AlertDialog) is deleted outright (D11):
  single-line replace also snapshots + toasts Undo.

## S6 - Auto-fit imposition (FE only)

- `ImpositionPreset` gains `'auto'`; `impositionFit(page_w, page_h, bleed, gap,
  tag_w, tag_h) => {cols, rows, perSheet}` = `floor((usable + gap) / (tag +
  gap))` per axis, usable = page - 2*bleed; 0 when a tag does not fit.
- `impositionSlots` gets one branch: `auto` (and, for old docs, `a4_3up` /
  `a4_2x2` route to auto too - AC-S6-4); slots centred as today.
- `ArrangeSheetView`: remove the preset select; keep the four number fields;
  add the read-only fit line; empty state when perSheet = 0. On save,
  `preset` writes `'auto'`.
- `IMPOSITION_PRESETS` shrinks to `auto` + `custom` defaults (identical
  geometry); `'custom'` stays as the marker for "user edited page fields".

## Order and dependencies

S1 -> S2 -> S3 -> S4 -> S5 -> S6 as commits on one lane branch
`feat/price-tag-ux-r3` (one lane = one PR). S1-S3 and S5-S6 are FE only; S4
carries the migration. Each slice: Phase 1 mock where a BE call is new (S4
only), Phase 2 test-first, agent-browser evidence, then next slice.

Lane stack: needs one FE + BE slot; pick the free slot at kickoff (:3100/:8100
currently held by the r2 integration worktree - reclaim it first via
`scripts/worktree-gc.sh --apply --merged`).

## Testing seams

- Pure helpers, all vitest first: `canvas-panels.ts`, `text-format.ts`,
  `colour.ts`, `templateFromTag`, `applyDesignToAllLines`, `impositionFit`.
- pytest: tag sizes CRUD + auth + isolation; from-tag create+publish.
- Component vitest: `TagSizeControl` grouping, `InlineTextEditor` commit paths,
  `ColorPicker` hex input.
- Browser: one agent-browser evidence run per slice (AC-X-1).

## Out of scope (backlog)

- Per-character rich text; opacity; gradients; saved colour swatches; rotated
  tags in imposition; RGB/HSL numeric tabs; panel widths synced across devices.
