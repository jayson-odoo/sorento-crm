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
