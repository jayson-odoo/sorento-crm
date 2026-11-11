# PLAN: spec sheet designer parity, slice B

Status: in review, PR #2349 (full track: migration + new export surface). B1-B7 built; reviewer READY, security ready, browser passes done; UAC `spec-sheet-designer-parity-b-11nov-acceptance-criteria.md`; migration timed (UAC AC-M.2).
Branch `claude/spec-sheet-designer-parity-b2-2sv9bf`, PR #2349, on main after slice A (#2331)
merged as c3169d9c; the earlier PR #2336 is superseded.

Owner answers (11 Nov): 1 (a), 2 (c), 3 (a), 4 (a) through the standard export/download flow;
mock approved ("ok good", `mock-spec-sheet-designer-parity-11nov.html`); 15:40 ruling: a
"Spec sheet description" product field with a per-sheet override.

One designer: every element below lives in the shared Konva designer (`TagCanvasEditor`,
`KonvaTagLayer`, `InspectorPanel`, `TagSheetRenderer` print) and works on price tags too. No
spec-sheet fork.

## B1. Spec sheet description (field + per-sheet override). Migration.

- `products.spec_sheet_description` TEXT NULL (additive, alembic, down_revision = main head at
  push time). Product master: multi-line box beside the price tag description
  (`ProductSpecificationsTab.tsx`), saved through the product update route, audited by the
  product's existing `__audit_track__` (History tab).
- Variable `{{product.spec_sheet_description}}`: the field, else `products.description`, never
  blank when either exists. Carried on product tag data, price tag request rows, spec sheet rows
  (line + parts + accessories), like `description` in slice A.
- Per-sheet override: the sheet row (`_row`, JSONB `rows`, no migration) gains
  `description` (the page's main product) and `accessory_descriptions: {accessory key: text}`.
  The resolver prefers the override for that sheet only. Reader: double-click the text that
  prints it opens the same field box AREA/COMMENT use (`ReaderPage` `editableField`), with
  "Reset to product text" (clears the override).

## B2. Accessories box in spec sheet mode (owner 2c).

- Unhide the Accessories tool and inspector for spec sheet templates (`TagCanvasEditor`
  `onAddAccessories={specSheet ? undefined : ...}` and the card editor / save-template gates).
- Spec sheet rows put the page's picked lines on `line.accessories` as `TagAccessory`
  (kind `product`: code, name, brand, description, spec_sheet_description (override applied),
  dimensions, photo). `accessoriesOf` (`accessory-box.ts:102`) then needs no change.
- `TagAccessory` + `CardField` gain `brand`, `description`, `spec_sheet_description`,
  `dimensions`; card default for spec sheets: bold "BRAND CODE" then the spec sheet description.
- Any number, no slot count, no warning. Picked lines keep skipping their own page. Existing
  templates' per-layer Accessory 1..N bindings keep working (untouched code path).

## B3. Variables (owner 1a), one registry (`merge-fields.ts`).

`line.description`, `line.quantity`, `line.uom`, `line.technical_spec`, `line.notes`,
`line.item_label`, `doc.subject_title`, `doc.attn`, `doc.recipient`, `doc.project_code`,
`doc.page_no`, `doc.page_count`, `accessory.N.code|name|brand|description|spec_sheet_description|
dimensions`. Sources: slice A card in `PLAN-spec-sheet-designer-parity-11nov.md`. Spec sheet
rows carry the real quantity (today hard-coded 1, service `_blank_row`). Also: Insert field on the
spec sheet page's own Inspector (`ReaderInspector`, absent today).

## B4. Table element (owner 3a).

New layer kind `table` in the shared designer: rows x cols, per cell rich text with variables,
per-side border colour/width, padding, fill; row height = max(set, measured text); insert/delete
row/col and merge cells from the context menu; Inspector table + cell sections. One layout
module (`lib/dealer-kit/table-layout.ts`) used by canvas and print (the `accessory-box.ts`
pattern). Backend layer validation accepts `table` (`test_s1_every_layer_type...`).

## B5. PowerPoint export (owner 4a), standard export/download flow.

- Route `POST .../spec-sheets/{id}/export?format=pptx` -> `request_export(..., fmt="pptx")`:
  `DownloadService.create` + `enqueue_job` on `catalogue_render` (same as PDF,
  `project_spec_sheet_service.py:1986-2017`); the file lands in My Downloads
  (`components/my-downloads/MyDownloadsDrawer.tsx`). Reader Export menu: PDF | PowerPoint.
- Worker task `generate_spec_sheet_pptx`: opens the same print page the PDF renders (one
  resolver: merge fields resolve only in the frontend), reads the resolved per-page layers the
  print page exposes (`window.__tagSheetLayout`: box, text runs, style, image urls, table cells),
  builds the deck with python-pptx: text -> text boxes, images -> pictures (pre-cropped),
  shapes -> autoshapes, tables -> pptx tables with cell borders, page size -> slide size.

## Order and tests (tester first per item)

B1 -> B2 -> B3 -> B4 -> B5. Each: pytest for the backend fields/routes/migration, vitest for
resolver/layout/editor, then reviewer + security (uploads unchanged; new export route RBAC =
the PDF export's) + cloud browser pass at 1280 and 375.

## Re-based on main (11 Nov ~22:00): PR #2349 replaces #2336

#2331 was squash-merged (c3169d9c). Slice B's net change was applied as one commit on main
(branch `claude/spec-sheet-designer-parity-b2-2sv9bf`, PR #2349). Two items added by the owner's
slice A hand test:

## B6. Page toolbar on the spec sheet (owner hand test, 11 Nov)

The spec sheet page top bar gets the price tag designer's add-element toolbar: the shared
`CanvasToolbar` (`dealer-kit/tag-templates/components/CanvasToolbar.tsx`), not a copy. Tools
offered on a spec sheet page: Text, Image, Shape, Table, Accessories box, Badge (the ones that
make sense on a quotation page; Product / Set / Alternatives / Price badge / Barcode stay off,
their props are already optional or become optional), plus Undo / Redo / Delete / Duplicate /
Group / Ungroup, which act on the page the user last pressed (the paste target rule).
- The tools add to that page's canvas through the embedded controller (`EmbeddedController`
  gains the editor's own add handlers), so a new element is placed and selected exactly as in
  the template designer, and the page autosaves it as a page edit. The template is untouched.
- Dialogs the add handlers open (image / asset picker) render in embedded mode too.
- "Every page": with Apply to = Every page, an added element is added to every page of the sheet
  through the server (a new apply-all operation `add`, beside the existing move / restyle of an
  existing layer id); pages the server changed restart their canvases, as apply-all does today.

## B7. Reset to template keeps the old layers (older bug)

`ResetPageButton` takes `onReset` but `ReaderPage` never passes one: after "Reset to template"
the server drops the page override, but the reader keeps that page's draft, undo history and
live canvas layers, and the next edit saves the old layers back. Fix: on the reset's commit the
reader forgets that page's draft and history and restarts its canvas from the refreshed payload
(the same restart apply-all uses). Red test: edit, reset, edit again -> the save carries the
template's layers plus only the new edit.
