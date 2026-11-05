# CARD: price tag combo format (rich description, LP/SP templates, designer preview picture)

Lane PRICETAG-COMBO-FORMAT, 5 Nov 2026. Read of `origin/main` e25d9b65 (PRICETAG-LPSP #2158 merged) plus
the PRICETAG-COMBO-RENDER branch (#2172, open). Build waits for the owner's mock approval and #2172's merge.

Owner, 5 Nov ~09:35 MYT: "in the description I think need to be able to do formatting so it can look close
to their existing price tag, and the wording I think need to be able to toggle between LP and SP depending
on the selection, or we can tie 1 template to LP or 1 to SP then it is more flexible meaning 1 product or
combo can tie to 1 or more LP or SP template, cause for LP, there is no LP or SP wording like the SP
template, think we need to use our existing preview function for the pic here"

## What exists today (measured)

- **Description is plain text, one style per layer.** `product_combos.description` (Text,
  `app/models/product_combo.py:73`) and `products.price_tag_description` (`app/models/product.py:325`).
  The combo editor saves it from a plain `Textarea` on blur (`ProductCombosSection.tsx:152`, `:537-544`).
  The tag prints it through the `combo_description` slot (`lib/dealer-kit/product-block.ts:324-330`,
  falls back to the product's `price_tag_description`). A text layer has ONE face: bold, colour,
  underline apply to the whole layer (`KonvaTagLayer.tsx:593-614`, one Konva `Text` node; line breaks from
  the shared `textLayerLines`). The print page draws the same lines as DOM (`TagSheetRenderer.tsx`, "not
  Konva" by design). So "code bold, part name normal" is impossible today.
- **Rich text pieces already in the app:** `components/ui/rich-text-editor.tsx` (tiptap, emits HTML) and
  `lib/sanitize.ts` (DOMPurify, frontend only). There is NO backend HTML sanitiser.
- **Other readers of the description:** `tag_data_service.py:1092` (tag data), `product_combo_service.py:139`
  (combo API), `price_tag_request_service.py:2224` (blank check), `project_spec_sheet_service.py`
  (spec sheet PDF reads `price_tag_description`).
- **LP/SP today (PRICETAG-LPSP, merged):** each request line has `price_type` (`list` | `selling`,
  `price_tag.py:218`). A template is NOT typed: `dealer_kit.tag_template` has name, family, doc, print_size
  only (`dealer_kit.py:705-761`). A product / combo links 0..n templates with ONE default
  (`product_tag_template`, `combo_tag_template`, partial unique index on `is_default`, `dealer_kit.py:799-877`);
  `pick_template` takes the sent pick, else the default, else a lone link (`product_tag_template_service.py:104-118`).
  Today's LP vs SP difference lives only in the layers: a `price_badge` `list_only` / `promo` variant, or a
  text layer bound to `list_price` / `sell_price`, or LPSP's dual slots `price` + `price_label`
  (`product-block.ts:366-385`). Names such as "Small Price Tag LP" / "Bathroom Furniture SP" are only names.
- **Designer picture.** The "No image" box is `ImageContent` (`KonvaTagLayer.tsx:460-502`); its URL comes from
  `layerDisplay` -> `boundImageUrl` (`product-block.ts:1175`, `:1290-1298`). The eye on the frame appears only
  when a loose layer is bound to a slot in `PRODUCT_SLOTS` (`lib/dealer-kit/preview.ts:54-67`, `:154`), and
  that list has no `combo_*` slot. The eye opens `ProductPickDialog` (products / sets only,
  `TagCanvasEditor.tsx:1208-1262`). Combos are previewed through a SEPARATE "Preview combo" select above the
  canvas (`TagCanvasEditor.tsx:4671-4690`) which loads `GET /dealer-kit/products/{host}/tag-data?combo_id=`
  (`tag_data.py:72-91`); the combo photo leads the image list via `_lead_with_cover`
  (`tag_data_service.py:1216-1223`), signed by `gallery_images` (`product_images.py:139-199`). That is the
  one image pipeline: request preview, PDF and designer all read `images[].url` from tag-data.
  So a combo-only template like screenshot 3 shows "No image" until someone finds the separate select.

## Rules (proposed)

### A. Description formatting

A1. **Stored as text with one marker, never HTML.** `**bold**` inside the same Text columns
    (`product_combos.description`, `products.price_tag_description`); line breaks stay newlines. No schema
    change, no HTML stored, nothing to sanitise server-side: it is plain text with two asterisks. Every
    existing description stays valid and prints exactly as today.
A2. **Editor:** the existing Description box gains a Bold button (and Ctrl/Cmd+B) that wraps the selection in
    `**`; beside it, a live tag preview of this combo with its default template (same renderer as the PDF),
    so the user sees bold, not asterisks, before saving (Q1).
A3. **One parser, two renderers.** One function turns the text into lines of runs
    (`{text, bold}`); the canvas draws runs (Konva text per run) and the print page draws runs (`<span>`
    text nodes, never `innerHTML`). Line wrapping measures each run in its own face, so canvas, request
    preview and PDF break at the same place. Anything typed that looks like HTML (`<b>`) prints literally.
A4. **Colour comes from the template, not the description.** A text layer gains "Bold text colour"
    (default = the layer's colour). The flyer look (code black/green bold, part name and dimensions grey)
    is: layer colour grey, bold colour black. No per-word colour picker (Q2).
A5. **Bold is manual.** MIRROR and SHELF are bold on the flyer and are not codes, so auto-bold of catalogue
    codes cannot produce the flyer by itself. Existing combo descriptions get a one-time, dry-run-first
    script that bolds the first token of each line that resolves to a catalogue product code; owner approves
    the report before `--apply` (Q3).
A6. **Every other reader strips the marker.** One `plain_text()` helper (backend) used by the spec sheet,
    chatbot/MCP reads and any export, so no `**` ever reaches a customer outside the tag.
A7. **Never silent loss** (standing rule). Unpaired `**` prints literally. A bold run that crosses a newline
    closes at the line end. Overflow keeps today's layer fit rule; the live preview shows it before saving.

### B. LP / SP per template

B1. **A template has a price type:** `LP`, `SP` or `LP or SP`. New column `dealer_kit.tag_template.price_type`
    (`list` | `selling` | NULL = either). Set in the template's settings next to Family. An `LP or SP`
    template is one that uses LPSP's `price` / `price_label` slots and serves both (owner's Q1 a of 4 Nov keeps
    working).
B2. **Links are unchanged in shape:** a product or combo still links 1..n templates; now it can link several
    LP and several SP templates. **One default per price type** (one default LP, one default SP); the DB partial
    unique index on `is_default` becomes a service check per (owner, price type) (Q4).
B3. **The request line offers only matching templates.** LP line: LP templates + `LP or SP` templates.
    SP line: SP + `LP or SP`. Flipping the line's LP/SP switches to that type's default; if the current pick
    still matches it is kept.
B4. **No matching template = visible, not silent.** An SP line whose item has no SP (or either) template
    shows "No SP template linked" in the row, the eye is disabled, and Submit/Approve refuse the line with
    that reason. Never fall back to the other type's template (that is how an LP tag would print with SP
    wording or vice versa).
B5. **What prints:** unchanged renderer. An LP template prints only what its layers bind (typically
    `list_price` or a `list_only` badge: "RM 730", no "LP"/"SP" word unless designed in). An SP template prints
    what the flyer shows: a `list_price` text layer "LP: RM 730" plus the `promo` badge "SP RM 459".
B6. **Existing templates are classified from their layers, not their names:** `promo` badge or `sell_price`
    binding -> SP; only `list_only` badge / `list_price` binding -> LP; `price`/`price_label` or no price at all
    -> LP or SP. Dry-run report listing every template, its type and the name check (name says LP but layers
    say SP is flagged), owner approves before write. Existing request lines keep their stored template
    (approved tags keep their pinned data); only new picks are filtered.
B7. Cabana (no selling price brand): an SP line still needs a typed SP (LPSP R2); with it, SP templates are
    offered as for any item.

### C. Designer picture through the existing preview

C1. **The eye shows for combo templates too.** `combo_*` slots join `PRODUCT_SLOTS`, so a tag built from
    `{{combo.name}}`, `{{combo.description}}` and a combo photo layer gets the frame's eye.
C2. **One picker.** The eye's `ProductPickDialog` searches products AND combos (combos labelled "Combo",
    e.g. "SRTBF11416 Bathroom Furniture"). Picking a combo runs today's `handlePreviewCombo`
    (`tag-data?combo_id=`), so the picture is the combo photo from the same `gallery_images` signed URL that
    the request preview and the PDF use, drawn by the same `ImageContent`. The separate "Preview combo"
    select is removed (one entry point, Q5).
C3. **Preview data is never saved** (as today: `previews` is editor-only state).
C4. Edge: a combo with no photo shows its host product's primary photo (today's `_lead_with_cover` rule);
    a combo whose host has no photo at all shows "No image" plus the combo code, never a stale picture.
    An image layer with no binding stays a placeholder: the inspector's Product/Combo photo binding is how
    a layer gets a picture.

## Examples (real codes, from the owner's 4 screenshots and repo fixtures)

The dev database is not reachable from this cloud sandbox (crew contract: no shared DB), so the figures are
the owner's screenshots; the read-only SQL at the bottom lets crew confirm them on dev.

- **E1 SRTBF11416 (Bathroom Furniture combo, white), SP line, template "Bathroom Furniture SP".** Stored
  description: `**SRTBF11416** (CABINET)\nL400xW345xH390mm\n**SRTWB248** (BASIN)\nL430xW360xH150mm\n**MIRROR**\nL400xH500mm\n**SHELF**\nL400xH120mm\n**SRTWT5837**\n(BASIN COLD TAP)\n**SRTW2600**\n(POP UP WASTE)`.
  Prints: codes, MIRROR, SHELF bold in the bold colour; part names and dimensions normal in grey; "LP: RM 730";
  big "SP RM 459". Canvas, request preview and PDF identical.
- **E2 same combo, LP line.** The template list offers only LP / either templates (e.g. "Small Price Tag LP").
  Prints "RM 730" and the description; no SP block, no "LP"/"SP" word unless the template has one.
- **E3 SRTBF11415 (black sibling).** Same description shape with its own code; the dry-run bold script
  (A5) bolds SRTBF11415, SRTWB248, SRTWT5837, SRTW2600 (resolve in catalogue) and leaves MIRROR / SHELF for
  manual bold, listing them in the report.
- **E4 combo "SRTBF11829 + SRTMCB8083-BL" (LP 2,715, SP 2,099), no templates linked.** SP line row shows
  "No SP template linked"; eye disabled; Submit refuses with that reason. Linking "Bathroom Furniture SP" to
  it makes the line printable.
- **E5 Designer, template "Bathroom Furniture SP".** Eye top right -> picker -> type "SRTBF11416" -> pick the
  Combo row -> image box shows the combo photo, `{{combo.name}}` -> the combo name, description bold per E1,
  badge SP RM 459. Close the template without saving: nothing about SRTBF11416 is stored on it.

## Questions (each with a recommendation)

- **Q1 Description editor.** (a) the existing text box + a Bold button, stored as `**bold**`, with a live tag
  preview beside it; (b) a WYSIWYG box (our `RichTextEditor`, bold only) that shows bold directly and saves the
  same `**` text. **Recommend (a)**: no new editor surface, the live preview is exactly what prints, and the
  box stays pasteable from Excel / AI extract.
- **Q2 Colour.** (a) bold only, plus a "Bold text colour" on the template's text layer (normal text grey, bold
  black, as the flyer); (b) per-word colour from the template palette inside the description. **Recommend (a)**:
  matches the flyer with one template setting, and every combo using the template stays consistent.
- **Q3 Existing descriptions.** (a) manual bold, plus a one-time dry-run script that bolds catalogue codes at
  line starts (owner approves the report); (b) manual only. **Recommend (a)**: most of the effort is bolding
  codes, and MIRROR/SHELF-style words are reported for a quick manual pass.
- **Q4 Template price type and defaults.** (a) each template is LP, SP or "LP or SP", classified from its
  layers with a report before writing; each product/combo has one default LP and one default SP template;
  (b) classify by the name suffix "LP"/"SP". **Recommend (a)**: names are free text and can lie; the layers are
  what actually print.
- **Q5 Designer preview entry.** (a) the eye's picker finds products and combos, and the separate "Preview
  combo" box goes; (b) keep both: eye for products, the box for combos, and only make the eye appear on combo
  templates. **Recommend (a)**: one way to preview, the eye you already pointed at.

## Crew read-only check on dev (optional)

```sql
-- templates and what their layers say (price type evidence)
SELECT t.name,
       t.doc::text LIKE '%"variant": "promo"%' OR t.doc::text LIKE '%"sell_price"%' AS has_sp,
       t.doc::text LIKE '%"list_only"%' OR t.doc::text LIKE '%"list_price"%' AS has_lp,
       t.doc::text LIKE '%"price_label"%' AS has_dual,
       t.published_version_id IS NOT NULL AS published
FROM dealer_kit.tag_template t ORDER BY t.name;
-- the real case
SELECT c.name, c.list_price, c.sell_price, c.description
FROM product_combos c JOIN products p ON p.id = c.host_product_id
WHERE p.product_code IN ('SRTBF11416','SRTBF11415','SRTBF11829');
```

## Track

Full track (migration: `tag_template.price_type`, index change on the two link tables; rendering change in
both renderers; security review for the text-to-runs path even though no HTML is stored).
