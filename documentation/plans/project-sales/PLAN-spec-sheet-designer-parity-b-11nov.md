# PLAN: spec sheet designer parity, slice B

Status: Plan (full track: migration + new export surface). Branch
`claude/spec-sheet-designer-parity-b-2sv9bf`, PR "SPEC-SHEET-DESIGNER-PARITY B:". Slice A is
PR #2331 (frozen at 716f0cb7 for the owner's hand test); this branch starts from that head.

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
