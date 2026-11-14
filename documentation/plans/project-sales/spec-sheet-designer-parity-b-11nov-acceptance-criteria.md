# UAC: spec sheet designer parity, slice B (PR #2349)

Plan: `PLAN-spec-sheet-designer-parity-b-11nov.md`. Owner answers 11 Nov: 1a, 2c, 3a, 4a; spec
sheet description ruling; page toolbar ask. Hand test: `laneboard/scripts/2349.md`.

## B1 Spec sheet description
- AC-B1.1: Product > Specifications has a multi-line "Spec sheet description"; saved through the
  product update, recorded in the product History, cleaned like the price tag description, at most
  20000 characters.
- AC-B1.2: `{{product.spec_sheet_description}}` prints the field, else the product description,
  else nothing; for the line product, its parts and its accessories; price tag requests too.
- AC-B1.3: on a spec sheet page, double-clicking a text that prints it opens a multi-line box;
  saving overrides it for that spec sheet only (product and other sheets unchanged); "Reset to
  product text" removes the override. Same for an accessory card's text (keyed by product).
- AC-B1.4: a save that does not send the override keeps the stored one; an empty string resets.

## B2 Several products on one page (2c)
- AC-B2.1: the price tag Accessories box can be added on spec sheet templates and behaves exactly
  as on price tags (one box, N cards, vertical / horizontal, columns, picture above / beside).
- AC-B2.2: on a spec sheet page it lists the set parts, then the lines picked with "Add accessory",
  any number, no slot limit, no warning; picked lines do not get their own page.
- AC-B2.3: the default spec sheet card is picture, bold "BRAND CODE", spec sheet description.
- AC-B2.4: existing templates' per-layer Accessory 1..N bindings keep working.

## B3 Variables (1a)
- AC-B3.1: one registry for both designers, incl. product.description, doc.project_title, doc.ref,
  line.area, doc.prepared_by, doc.date, line.comment, plus line.description / quantity (real) /
  uom / technical_spec / notes / item_label, doc.subject_title / attn / recipient / project_code /
  page_no / page_count, accessory.N.code|name|brand|description|spec_sheet_description|dimensions.
- AC-B3.2: price tag templates do not offer the spec-sheet-only fields; a missing value prints
  empty, never the token.
- AC-B3.3: the spec sheet page Inspector has Insert field; on formatted text it inserts at the
  caret and never shows markup.

## B4 Table element (3a)
- AC-B4.1: Add Table in both designers; right-click insert / delete row and column, merge right,
  merge down, unmerge; clicking a cell selects it in the Inspector.
- AC-B4.2: per cell: text with variables, border colour and width per side or all sides, padding,
  fill; a shared border is drawn once and editing either cell's side changes it; rows grow to fit
  long text; canvas and print lay the table out the same.
- AC-B4.3: every save path refuses a table over 50 x 50, a mismatched grid, or a colour that is
  not a plain colour.

## B5 PowerPoint (4a)
- AC-B5.1: Export > PowerPoint creates a row in the Downloads tray (same flow and permission as the
  PDF) that turns ready; the file has one slide per printed page at the page size.
- AC-B5.2: text boxes are editable (font, size, colour, bold), pictures are pictures, tables are
  real tables (merges, borders), the Accessories box and price badge come through; barcodes do not.
- AC-B5.3: the worker fetches only images the print page loaded, capped in size; no other URL.

## B6 Page toolbar
- AC-B6.1: the spec sheet page shows the shared price tag toolbar with Text, Image, Shape, Table,
  Accessories, Badge, Undo, Redo, Delete, Duplicate, Group, Ungroup; one Undo on the page.
- AC-B6.2: an added element lands on the page last pressed and is saved for that page only; the
  template is unchanged.
- AC-B6.3: with Apply to = Every page it is added once to every product page (cover only from the
  cover), never twice; an image or badge is sent only once its picture is chosen; a cancelled
  picker leaves no empty frame; later Every page moves reach those copies.
- AC-B6.4: pages whose template has an Accessories box (or feature icons) save normally.

## B7 Reset to template
- AC-B7.1: after "Reset to template" the page shows the template and the next edit saves the
  template layers plus that edit only, never the old layers.

## Migration
- AC-M.1: `ssd_0001_product_spec_desc` adds `products.spec_sheet_description TEXT NULL`
  (`ADD COLUMN IF NOT EXISTS`), single alembic head on top of main.
- AC-M.2: timed on a 1,000,000-row / 559 MB synthetic products table (PostgreSQL 16, sandbox):
  0.8 ms; a re-run is a 1.9 ms no-op. Nullable with no default is a catalogue-only change (no
  table rewrite); its only risk is the brief ACCESS EXCLUSIVE lock waiting behind a long
  transaction on `products`.
