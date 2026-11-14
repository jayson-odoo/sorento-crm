# UAC: price tag designer feedback B (14 Nov)

Plan: `PLAN-pricetag-designer-feedback-b-14nov.md`. Owner answers: Q1 (c), Q2 (b), Q3 (a), Q4 never hide, Q5 one box per image.
Phase B1 = files #2349 does not touch. Phase B2 (after #2349 merges) wires them into the inspector, canvas, print page and backend layer schema, and adds item 3 and item 8.

## Phase B1

### AC-1 Font per word (shared rich-text editor, text layout, sanitiser)
- AC-1.1 `parseRichText` (lib/dealer-kit/rich-text.ts) reads `font-family` and `font-size` (pt) from a span's inline style into the run: `<p>A <span style="font-family: Montserrat; font-size: 14pt">B</span></p>` gives runs "A " (no font fields) and "B" (fontFamily "Montserrat", fontSize 14). Runs with different font fields are never merged.
- AC-1.2 `runFace` (lib/dealer-kit/text-layout.ts) uses the run's fontFamily and fontSize when set (the run size is used as given, no heading factor), else the layer's as today. Measured widths use that face.
- AC-1.3 Line height: a laid-out line containing a 14pt run in a 7pt layer is taller than a line of only 7pt text (line height follows the tallest run on the line); lines without run sizes are unchanged.
- AC-1.4 Shared `RichTextEditor` accepts an optional `fontOptions: { value: string; label: string }[]`. With it, the inline and full toolbars show a font picker (SearchableSelect-style, clearable) and a size field in pt. Selecting text, picking "Montserrat" and size 14 gives HTML `<span style="font-family: Montserrat; font-size: 14pt">` around exactly the selection; clearing removes the mark. Without `fontOptions` the toolbar is unchanged.
- AC-1.5 Backend sanitiser (app/utils/tag_rich_text.py) keeps `font-family` (a plain family name: letters, digits, spaces, hyphens, optional quotes; nothing else) and `font-size` (number + pt, 4 to 200) on span; anything else in those properties (url(), expression, semicolons injected) is dropped.

### AC-6 Pick and upload several images (AssetPickerDialog)
- AC-6.1 The upload drop zone accepts several files at once (same types and 20 MB per-file limit); each file is uploaded with the existing `uploadAsset` (one call per file, in order) and all appear in the library. A file over the limit or of a wrong type is named in a notice and the others still upload.
- AC-6.2 New optional `onPickMany(sources: ImageSource[])`: with it, tiles toggle a tick, the footer shows "N selected" and one filled "Done" button returns the picked sources in pick order; files uploaded in this mode are added to the selection. Without it, pick mode is unchanged (one click picks and closes) and select mode (`onDone`) is unchanged.

### AC-7 Spec icon rows (pure layout, lib/dealer-kit/feature-icons.ts)
- AC-7.1 New `featureIconGrid(count, { iconSize_mm, gap_mm, align, columns?, rows? }, boxWidth_mm, boxHeight_mm)` returns `{ positions: {x_mm, y_mm}[], iconSize_mm, height_mm, overflow }`. Positions are row-major, left to right.
- AC-7.2 Columns and rows: `columns` fixes icons per row; `rows` fixes the row count (columns = ceil(count / rows)); both auto = as many per row as fit, wrapping to new rows. 7 icons, rows 2 -> 4 on row 1, 3 on row 2.
- AC-7.3 Never hide (owner Q4): every icon gets a position (positions.length === count). If the grid needs more height than the box, icons shrink down to a minimum readable size (4 mm), then the grid grows: height_mm exceeds the box and `overflow` is true (the canvas will show a warning in B2).
- AC-7.4 `align` applies per row (left, center, right); rows are stacked from the top with `gap_mm` between them.
- AC-7.5 `featureIconRow` keeps its current behaviour for existing callers until B2 switches them.

## Phase B2 (after #2349 merges; red tests may land earlier in new test files)

### AC-3 Accessory photo per main product + accessory link (owner Q1 c)
- AC-3.1 Migration adds nullable `product_accessories.photo_attachment_id` (FK attachments.id, ON DELETE SET NULL). One column: a library asset and a product photo both resolve to an attachment.
- AC-3.2 `PUT /api/v1/products/{product_id}/accessories` row payload accepts `photo_attachment_id` (null clears it) for both kinds of row (library accessory and catalogue product); the list GET returns it. An attachment the caller cannot see is refused (404, same gate as product photos and kit assets).
- AC-3.3 Tag data: a row with `photo_attachment_id` set prints that photo as the card picture (`image` and `images[0]`) for both kinds of row, ahead of the per-row `image_id` and the product's lead photo; cleared, it falls back exactly as today.
- AC-3.4 Designer: right-click an accessory card on the canvas -> "Change photo" opens "Choose an image" (product photos of the accessory product, asset library, upload); the pick saves to that main product's list row. "Reset to product photo" appears only when an override is set and clears it. Every tag of that main product shows the new photo after reload.

### AC-5 Accessories box rows, AC-7.6 Spec icons box rows
- AC-5.1 Accessories box props gain `rows?: 'auto' | 1 | 2 | 3 | 4` beside `columns`; the inspector shows "Columns" and "Rows" selects (Auto, 1-4); the old "One column or row" label is gone. Backend layer schema accepts `rows`.
- AC-5.2 Columns Auto + Rows 2 with 5 cards: 2 rows (3 + 2), filled left to right. Columns 2 + Rows Auto with 5 cards: 3 rows (2, 2, 1).
- AC-5.3 Never hide (owner Q4): every card is laid out; cards shrink to a minimum readable size, then the box grows; a card that would cross the tag edge shows a visible warning on the canvas naming it. No silent drop.
- AC-7.6 Spec icons box gains the same Columns/Rows selects and lays out with `featureIconGrid` on the canvas and the print page; an overflow shows the same canvas warning.

### AC-8 Spec icon choice per product on each tag (owner Q2 b)
- AC-8.1 Spec icons layer props gain `hiddenIconIds?: string[]` (asset ids); the backend layer schema accepts it.
- AC-8.2 The inspector lists the icons this tag's product would show, each with a checkbox (ticked = shown). Unticking hides that icon on this tag only; other tags of the same template are unaffected.
- AC-8.3 Canvas and print skip hidden icons; the remaining icons close up.

### AC-1.6 to 1.8 Font per word wired
- AC-1.6 The Inspector's description/content editor passes the inspector's font list (`library.fontOptions`, uploaded fonts included) as `fontOptions`.
- AC-1.7 Print parity: the print page draws a run's fontFamily and fontSize exactly as the canvas (`runFace`); a 14pt Montserrat word prints in Montserrat 14pt.
- AC-1.8 Accessory cards scale run sizes with the card (a card scaled to 50 % draws a 14pt run at 7pt).

### AC-6.3 One box per picked image
- AC-6.3 Adding an image from the canvas toolbar opens the picker with `onPickMany`; picking 3 images adds 3 image boxes, each placed below the previous one, all selected. Replacing an existing box's image stays single-pick.
