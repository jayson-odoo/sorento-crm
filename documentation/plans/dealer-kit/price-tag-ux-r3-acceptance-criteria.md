# UAC - Price Tag Designer UX Round 3

Plan: `documentation/plans/dealer-kit/PLAN-price-tag-ux-r3.md`
Predecessors: `PLAN-price-tag-feedback-r2.md` (shipped #549), `PLAN-price-tag-request.md` (shipped #289)

## Journey

Actor: marketing designer (CRM user with `dealer_kit.tag_templates.manage`), on
`/dealer-kit/price-tag-requests/{id}/design`, arriving from the request's Lines
tab via a row's Design action.

1. The page opens with the Lines rail + Layers on the left, canvas centre,
   Inspector right. The designer drags the left or right panel edge to widen it,
   or collapses a side entirely to give the canvas room. The next visit opens with
   the same widths.
2. They double-click a text box on the canvas and type in place. Cmd/Ctrl+B,
   I, U and Cmd/Ctrl+Shift+X toggle bold / italic / underline / strikethrough on
   that box. The Inspector's Font Size and Font Weight still refine it.
3. They pick a colour from a spectrum square + hue bar, from the eyedropper
   pointed at the product photo, or from a colour already used on this tag.
4. They set the tag size to Custom 95 x 44.5 and click "Save as size", name it
   "Shelf rail"; it is now a preset for every future request. Presets are also
   listed and editable at `/dealer-kit/tag-sizes`.
5. Happy with the design, they click "Save as template", accept the prefilled
   name + family, and the template is created and published, ready in the
   "Use template..." picker on any request.
6. They click "Apply this design to all lines": every other line receives a copy
   of this tag, product bindings resolve per line, hand-typed overrides copy
   verbatim. An Undo toast reverts it.
7. In Arrange, the sheet fits as many tags as the page allows from the tag's own
   size, showing "2 x 6 = 12 per sheet, 1 sheet". Nothing to choose.
8. Autosave and Mark proof ready behave as before.

Derived, never asked: template family (from the line), template print_size
(from the tag), "This tag" colours, imposition grid.

## Decisions (grilled 3 Sep 2026)

- D1 Save as template strips `text_override` on bound layers; slot bindings
  stay generic; unbound text stays verbatim. Publishes immediately as v1.
- D2 Tag size presets = new table `dealer_kit.tag_size_preset`, company-scoped,
  with a listing page at `/dealer-kit/tag-sizes`; dropdown = published template
  sizes (not deletable) + saved presets (deletable) + Custom.
- D3 Apply template / design to all lines = replace immediately, Undo toast
  (deferred-action pattern), no confirm dialog. Both surfaces: Lines rail
  "Apply this design to all lines" (selected tag, edits included, overrides
  copied VERBATIM) and the template picker's "Apply to all lines" toggle
  (pristine template).
- D4 Text formatting is whole-layer: `italic`, `underline`, `strikethrough`
  booleans on `TextLayerProps`; Cmd+B toggles weight `>= 600 -> 400` else `-> 700`;
  weight select stays for fine control.
- D5 Inline edit = positioned textarea over the Konva node. Enter = newline,
  Esc / click outside / Cmd+Enter = commit. On a bound layer it edits
  `text_override` (Relink clears), same rule as the inspector.
- D6 Colour picker: saturation/value square + hue bar + hex + eyedropper
  (`EyeDropper` API, hidden when unsupported) + "This tag" row (auto) + Brand
  row (the existing 12). No opacity, no saved-swatch row.
- D7 Panels: left column (Lines + Layers) and right column (Inspector) each
  collapse + drag-resize via the existing `components/ui/resizable.tsx`; Lines
  vs Layers split inside the left column is a draggable horizontal divider.
  Widths in localStorage, one key shared by the template editor and the request
  designer.
- D8 Imposition: the three presets are replaced by auto-fit (cols x rows from
  the largest tag on the page size); page / bleed / gap fields stay; the fit is
  shown as read-only text.
- D9 Tag sizes page reuses `dealer_kit.tag_templates.view` / `.manage`; no new
  permission slug, no grant sweep. Menu entry uses `dealer_kit.page.view` like
  its siblings.
- D10 Cmd+B rule confirmed: weight `>= 600 -> 400`, else `-> 700` (500 -> 700).
- D11 The single-line "Use template" confirm dialog is dropped too: replace +
  Undo toast everywhere (one behaviour for one line and for all lines).

## S1 - Panels collapse + resize [FE]

- AC-S1-1 [FE] Given the request designer at 1280px, when I drag the left
  column's right edge, then the Lines + Layers column resizes between 180px and
  480px and the canvas refits.
- AC-S1-2 [FE] Given the designer, when I drag the Inspector's left edge, then
  it resizes between 200px and 480px.
- AC-S1-3 [FE] Given either side column, when I click its collapse chevron,
  then the column collapses to a 24px strip with a single expand button, and
  clicking that restores the previous width.
- AC-S1-4 [FE] Given the left column, when I drag the divider between Lines and
  Layers, then the split moves; neither pane can shrink below 96px.
- AC-S1-5 [FE] Given I resized or collapsed panels, when I reload the page or
  open the tag template editor, then the same widths and collapsed state apply
  (localStorage key `dealer-kit.canvas-panels.v1`).
- AC-S1-6 [FE] Given a reduced-motion preference, collapse/expand has no
  animated width transition.
- AC-S1-7 [FE] Given 375px, panels stay hidden as today (no regression).
- AC-S1-8 [T] Vitest: the layout-state helper (parse/serialise/clamp) is unit
  tested; a corrupt localStorage value falls back to defaults.

## S2 - Inline text edit + B/I/U/S [FE]

- AC-S2-1 [FE] Given a text layer, when I double-click it, then a textarea
  appears over the node at the node's position, size, font, alignment and
  zoom, focused with the caret at the end.
- AC-S2-2 [FE] Given the inline editor, when I press Enter, then a newline is
  inserted; Esc, Cmd/Ctrl+Enter or clicking outside commits and closes it.
- AC-S2-3 [FE] Given a slot-bound text layer, when I edit inline and commit,
  then `text_override` is set (the inspector shows the override + Relink), and
  Relink clears it.
- AC-S2-4 [FE] Given a text layer selected (edit mode or not), when I press
  Cmd/Ctrl+B, then `fontWeight` toggles per D4; Cmd/Ctrl+I toggles `italic`;
  Cmd/Ctrl+U toggles `underline`; Cmd/Ctrl+Shift+X toggles `strikethrough`.
  With several text layers selected, all toggle to the same target state.
- AC-S2-5 [FE] Given the inspector's Text section, then a B / I / U / S toggle
  group sits beside Font Size; pressed state reflects the layer.
- AC-S2-6 [FE] Given italic/underline/strikethrough set, then the Konva canvas
  renders them (`fontStyle`, `textDecoration`).
- AC-S2-7 [FE] Given italic/underline/strikethrough set, then the print
  renderer (`TagSheetRenderer`) renders them in the PDF.
- AC-S2-8 [FE] Given the inline editor is open, existing single-key shortcuts
  (V, H, Space, Delete, arrows) do NOT fire.
- AC-S2-9 [T] Vitest: `toggleBold` / `toggleTextFlag` pure helpers; a layer
  missing the new flags (old docs) reads as false.

## S3 - Colour picker [FE]

- AC-S3-1 [FE] Given a colour field in the inspector, when I click the swatch,
  then a popover opens with a saturation/value square, a hue bar, a hex input,
  an eyedropper button, a "This tag" row and a "Brand" row (per the approved
  mockup).
- AC-S3-2 [FE] Given the popover, when I drag in the square or on the hue bar,
  then the field's hex updates live and the canvas repaints on release.
- AC-S3-3 [FE] Given the hex input, when I type a valid 3- or 6-digit hex, then
  the square/hue reflect it; invalid input is ignored on blur.
- AC-S3-4 [FE] Given a browser with `window.EyeDropper`, when I click the
  eyedropper and pick a pixel, then the field takes that colour; without the
  API the button is not rendered.
- AC-S3-5 [FE] Given the current tag uses N distinct colours across text, shape
  and badge layers, then "This tag" lists them (deduped, max 16, most-used
  first); clicking one applies it.
- AC-S3-6 [FE] Given the Brand row, then the existing 12 swatches still apply
  on click.
- AC-S3-7 [FE] The native `<input type="color">` is gone from the picker.
- AC-S3-8 [T] Vitest: hex <-> hsv conversion round-trips; `tagColours(layers)`
  dedupes and orders by frequency.

## S4 - Tag size presets + Save as template [BE + FE]

- AC-S4-1 [BE] Migration creates `dealer_kit.tag_size_preset` (id, company_id,
  name, width_mm, height_mm, created_by, created_at, updated_at) with a unique
  (company_id, name).
- AC-S4-2 [BE] `GET/POST /dealer-kit/tag-sizes`, `PUT/DELETE
  /dealer-kit/tag-sizes/{id}` behind `dealer_kit.tag_templates.view` (GET) and
  `.manage` (writes); company-scoped; a duplicate name is 409; width/height
  below 10mm is 422; unauthenticated is 401; a viewer without manage is 403.
- AC-S4-3 [FE] Given the tag size panel on a Custom size, then a "Save as size"
  button opens a name dialog and, on Save, the size appears selected in the
  dropdown under a "Saved sizes" group.
- AC-S4-4 [FE] Given the dropdown, then it groups "Template sizes" (from
  published templates, as today), "Saved sizes" (each with an x that deletes as a
  deferred action with Undo toast) and "Custom".
- AC-S4-5 [FE] `/dealer-kit/tag-sizes` listing: DataGrid (name, width, height,
  created by, updated), search, Add + Edit modal, delete with Undo toast; row
  actions (Edit, Delete) live in the row's `...` menu, never inline buttons; sidebar
  entry "Tag Sizes" under Dealer Kit next to Tag Templates; RecordNavigation not
  required (modal CRUD, no detail page).
- AC-S4-6 [FE] Given a designed tag, then the designer header has "Save as
  template" opening a dialog with name prefilled "<line code> tag" and family
  prefilled from the line, both editable.
- AC-S4-7 [BE] `POST /dealer-kit/tag-templates/from-tag` accepts {name, family,
  doc, print_size}, creates the template AND publishes v1 in one transaction,
  returns the template with `published_version_no = 1`; declared before
  `/{template_id}`.
- AC-S4-8 [FE] Given Save as template succeeds, then a toast "Template
  published" with an "Open" action to `/dealer-kit/tag-templates/{id}` shows, and
  the new template appears in this request's "Use template..." picker without
  reload.
- AC-S4-9 [FE] Given the saved tag had `text_override` on bound layers, then the
  template's layers carry no `text_override` (D1); unbound text is verbatim;
  group/children ids are remapped to fresh ids.
- AC-S4-10 [T] pytest for AC-S4-1/2/7 (happy, auth denial, validation,
  duplicate, company isolation); vitest for the strip-overrides helper.

## S5 - Apply design / template to all lines [FE]

- AC-S5-1 [FE] Given a line selected with a tag, then the Lines rail header has
  "Apply this design to all lines".
- AC-S5-2 [FE] Given I click it, then every other line's tag becomes a clone of
  the selected tag (layers, size, template_id), rebound to that line's
  product/set via `bindTemplateLayers`, with `text_override` values copied
  verbatim (D3); pinned Arrange positions are kept.
- AC-S5-3 [FE] Given the apply ran, then a toast "Applied to N lines" with Undo
  restores the previous tags map; Cmd/Ctrl+Z does the same.
- AC-S5-4 [FE] Given the "Use template..." dialog, then an "Apply to all lines"
  checkbox (default off) applies the chosen template to every line instead of
  one, with the same Undo toast; no confirm dialog either way (edited tags are
  replaced; Undo is the safety).
- AC-S5-7 [FE] Given a single line with an edited tag, when I pick a template
  for it, then it is replaced immediately with an Undo toast; the
  "Replace this tag with the template?" dialog no longer exists (D11).
- AC-S5-5 [FE] Given a line not yet opened (no tag cloned), then apply-to-all
  creates its tag too, so it does not later re-clone from the default template.
- AC-S5-6 [T] Vitest: `applyDesignToAllLines(tags, lines, sourceLineId)` pure
  helper: rebinding per line, verbatim overrides, pinned kept, fresh layer ids.

## S6 - Auto-fit imposition [FE]

- AC-S6-1 [FE] Given Arrange view, then the Preset select is gone; Page W/H,
  Bleed, Gap remain, plus a read-only line "C x R = N per sheet, S sheets".
- AC-S6-2 [FE] Given tags 95 x 44.5 on A4 (210 x 297, bleed 3, gap 2), then the
  fit is 2 x 6 = 12 per sheet, and 10 lines yield 1 sheet.
- AC-S6-3 [FE] Given a page too small for one tag, then the fit reads "0 per
  sheet" and the Arrange canvas shows an explicit empty state with the reason.
- AC-S6-4 [FE] Given an old doc with `imposition.preset = 'a4_3up' | 'a4_2x2'`,
  then it loads and lays out via auto-fit (preset ignored, migrated to
  `'auto'` on next save).
- AC-S6-5 [FE] Pinned copies keep their positions; unpinned copies flow into
  the auto-fit grid in line order.
- AC-S6-6 [T] Vitest: `impositionFit(page, bleed, gap, tagW, tagH)` golden set
  (the 2 x 6 case, a 1 x 1 case, a 0 case).

## Cross-cutting

- AC-X-1 [E2E] agent-browser evidence run per slice on the dev server via the
  sidebar path Dealer Kit > Price Tag Requests > row > Lines > Design, at 1280px;
  screenshots of golden path + one edge case each; console clean.
- AC-X-2 [FE] The template editor (`/dealer-kit/tag-templates/{id}`) gains S1,
  S2 and S3 for free through `TagCanvasEditor`; verify once.
- AC-X-3 [T] Full `npm run test` and backend pytest green before push;
  `alembic heads` single head on the lane after merging main.
