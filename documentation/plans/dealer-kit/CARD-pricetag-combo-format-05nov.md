# CARD v2: price tag combo format (rich description, LP/SP templates, combo photo preview)

Lane PRICETAG-COMBO-FORMAT, 5 Nov 2026. Read of `origin/main` e25d9b65 (PRICETAG-LPSP #2158 merged) plus
the PRICETAG-COMBO-RENDER branch (#2172, open). Build waits for the owner's approval of mock v2 and #2172's
merge.

Owner, 5 Nov ~09:35 MYT: "in the description I think need to be able to do formatting so it can look close
to their existing price tag, and the wording I think need to be able to toggle between LP and SP depending
on the selection, or we can tie 1 template to LP or 1 to SP then it is more flexible meaning 1 product or
combo can tie to 1 or more LP or SP template, cause for LP, there is no LP or SP wording like the SP
template, think we need to use our existing preview function for the pic here"

## Owner answers to card v1 (5 Nov ~10:00 MYT, verbatim)

"Q1 we should reuse our existing rich text formatting engine la, not just bold, Q2 again, should reuse our
rich text formatting engine which should have colour also, we need to have a complete rich text editor, Q3
all by hand, Q4 should be hand selected la the LP or SP or LP & SP, Q5 hmm I actually mean like I cna
preview the photo of the combo, not the price tag of the combo"

Mock v1 notes (09:46): "should reuse our formatting engine in the system, not just bold la"; "should be
LP & SP"; "the rest all good".

So: A = the app's rich text editor, made complete (colour included) in the shared engine; no bold script;
B = price type picked by hand; C = the combo photo opens full size in the app's image preview. The v1
designer changes (eye on combo templates, one picker) are dropped; the designer's "Preview combo" select
stays as today.

## What exists today (measured)

- **Description is plain text, one style per layer.** `product_combos.description` (Text,
  `app/models/product_combo.py:73`) and `products.price_tag_description` (`app/models/product.py:325`).
  The combo editor saves it from a plain `Textarea` on blur (`ProductCombosSection.tsx:152`, `:537-544`).
  The tag prints it through the `combo_description` slot (`lib/dealer-kit/product-block.ts:324-330`).
  A text layer has ONE face (`KonvaTagLayer.tsx:593-614`, one Konva `Text`; lines from `textLayerLines`);
  the print page mirrors it as DOM (`TagSheetRenderer.tsx`).
- **The rich text engine:** `components/ui/rich-text-editor.tsx` (tiptap 3 `StarterKit` + `Link`, plus
  `Mention` when asked), used by 8 screens (tickets, email templates, quotation letters / templates / cover).
  Toolbar (`:185-300`): Bold, Italic, Strikethrough, Inline code, H1-H3, Bullet list, Numbered list,
  Blockquote, Link, Undo, Redo. **No colour, no underline button, no alignment.** It emits HTML
  (`editor.getHTML()`, `:558`; empty = "", `:559`). Display elsewhere goes through `lib/sanitize.ts`
  (DOMPurify, frontend only). **The backend has no HTML sanitiser.**
- **A colour control exists:** the tag designer's `ColorPicker`
  (`app/(protected)/dealer-kit/tag-templates/components/ColorPicker.tsx`: spectrum, hex, eyedropper, brand
  swatches), no dependency.
- **LP/SP today (PRICETAG-LPSP, merged):** each request line has `price_type` (`list` | `selling`,
  `price_tag.py:218`). A template has no type (`dealer_kit.py:705-761`). A product / combo links 0..n
  templates with ONE default (`product_tag_template`, `combo_tag_template`, partial unique index on
  `is_default`, `dealer_kit.py:799-877`); `pick_template` = sent pick, else default, else a lone link
  (`product_tag_template_service.py:104-118`).
- **Combo photo:** a 56 px thumbnail with Replace / Clear (`ProductCombosSection.tsx:362-390`), no click
  action. Its URL is already the full-size signed original (`product_combo_service.py:112-130`,
  `{attachment_id, url}`). The app's image preview is `components/common/AttachmentPreviewModal.tsx`
  (zoom, download; used by price tag requests, packing lists, stock inquiries, purchase requests, loading
  plan, chat history, chatbot console).

## Rules (proposed)

### A. Description = the app's rich text editor, complete

A1. **One engine, made complete for everyone.** `RichTextEditor` gains, in the shared component (not a
    tag-only fork): **Text colour** (the designer's `ColorPicker`, moved to `components/common/ColorPicker.tsx`
    so there is one colour control; swatches = brand colours + "Remove colour"), **Highlight** (same picker),
    an **Underline** button, and **Align left / centre / right**. New tiptap packages:
    `@tiptap/extension-text-style` (TextStyle, Color, BackgroundColor), `@tiptap/extension-text-align`, and
    `@tiptap/extension-underline` only if StarterKit 3 does not already carry the mark (checked at build),
    same 3.22 line as the installed tiptap. All 8 existing screens get the new buttons (owner: "complete
    rich text editor").
A2. **Where it is used here:** the combo Description (`ProductCombosSection.tsx:537-544`) and the product's
    price tag description (`ProductSpecificationsTab.tsx:179`). Beside it, a live tag preview of this item
    with its default template (`DesignViewer`, the renderer the request preview uses). Save on blur as today.
A3. **Storage = sanitised HTML in the same Text columns.** No schema change for text. **Server-side
    allow-list on every write** (combo API, product API, importer, flyer re-seed, AI extract): elements
    `p br strong em s u code h1 h2 h3 ul ol li blockquote a span mark`; every attribute dropped except
    `style` holding ONLY `color` / `background-color` with a hex or `rgb()` value, and `text-align` with
    `left|center|right` on blocks; `a` keeps no `href` on tag fields. `script` / `style` / `iframe` / `object`
    are dropped with their content; any other tag is removed and its text kept. One helper,
    `app/utils/tag_rich_text.py` (`sanitise_tag_html()`, `plain_text()`), built on the standard library's
    `html.parser` (no new backend dependency).
A4. **One parser, every renderer, no innerHTML.** One FE function (`lib/dealer-kit/rich-text.ts`) turns the
    stored value into blocks of runs (`{text, bold, italic, underline, strike, code, color, highlight}`;
    block = paragraph / heading 1-3 / list item with bullet or number / quote, each with its alignment).
    The canvas (`KonvaTagLayer.tsx` `TextContent`), the request preview (`DesignViewer`) and the print/PDF
    page (`TagSheetRenderer.tsx`: React text nodes and `<span>`s, never `innerHTML` /
    `dangerouslySetInnerHTML`) all draw that model; `textLayerLines` wrapping becomes run-aware so all three
    break lines at the same place. Colours are re-validated by the parser (hex / rgb only) before drawing.
A5. **What each item prints on a tag** (face and base size from the template layer): bold, italic,
    underline, strikethrough, colour, highlight as marked; inline code in a monospace face; Heading 1 / 2 / 3
    bold at 1.4x / 1.2x / 1.1x; bullet "•" and numbered "1." with a hanging indent; quote indented; alignment
    per paragraph (unset = the layer's alignment); a link prints its text. Nothing is dropped.
A6. **Font and base size stay the template's** (Q1), so every combo on one template keeps the same layout;
    headings give the bigger sizes.
A7. **Legacy plain text stays valid.** A stored value that does not start with an allowed block tag is plain
    text: each line is a paragraph. It prints exactly as today; opening it in the editor shows the same lines;
    saving writes HTML. No data migration, no script: existing descriptions are formatted by hand (Q3 b).
A8. **Every non-tag reader gets plain text** via `plain_text()` (keeps line breaks, "• " and "1. "; drops all
    markup): spec sheet (`project_spec_sheet_service.py`), chatbot / MCP reads, importer dry-run report, any
    xlsx export.
A9. **Merge fields stay safe.** `price_tag_description` holds merge fields (`{{...}}`); they resolve on TEXT
    runs after parsing, so a spec value containing `<` prints as `<` and never becomes markup.
A10. **Never silent loss.** Overflow keeps today's layer fit rule; the live preview shows it before saving.

### B. LP / SP per template, picked by hand

B1. **A template has a price type, chosen by hand** in the template settings next to Family:
    `LP`, `SP` or `LP & SP` (owner Q4). New nullable column `dealer_kit.tag_template.price_type`
    (`list` | `selling` | `both`). No classification from layers, no name parsing.
B2. **Existing templates start unset.** The template list shows a "Set price type" badge on them. Until set,
    an unset template is offered on both LP and SP lines, exactly like today, so nothing changes on release.
    The template list can be filtered to "Price type: not set" so the owner can work through them.
B3. **Links:** a product or combo links 1..n templates (several LP, several SP). **One default LP and one
    default SP** per product / combo; an `LP & SP` or unset template can be the default for either. The DB
    partial unique index on `is_default` becomes `default_for` (`list` | `selling`) on the link, unique per
    (owner, default_for); today's default becomes the default for both on migration.
B4. **The request line offers only matching templates.** LP line: LP + LP & SP + unset. SP line: SP +
    LP & SP + unset. Flipping the line's LP/SP switches to that type's default; a current pick that still
    matches is kept.
B5. **No matching template = visible, not silent.** An SP line whose item has no SP-capable template shows
    "No SP template linked" in the row, the line's preview eye is disabled, and Submit / Approve refuse the
    line with that reason. Never fall back to an LP-only template (or the reverse).
B6. **What prints:** the renderer is unchanged. An LP template prints what its layers bind (e.g. "RM 730",
    no "LP"/"SP" word unless designed in). An SP template prints the flyer: "LP: RM 730" and the big
    "SP RM 459". An LP & SP template uses LPSP's `price` / `price_label` slots and prints whichever the
    line is.
B7. Changing a template's price type never rewrites existing request lines; approved tags keep their pinned
    data. Only new picks are filtered.
B8. Cabana (no selling price brand): an SP line still needs a typed SP (LPSP R2); with it, SP templates are
    offered as for any item.

### C. Combo photo opens full size (owner Q5)

C1. In the product page's Combos section, clicking the combo photo thumbnail (beside Replace / Clear) opens
    `AttachmentPreviewModal` with that photo full size (zoom, download), the same component used for photos
    on the price tag request and elsewhere. Item = `{id: image.attachment_id, name: combo name, url:
    image.url}`; the URL is already the signed original, so there is no new endpoint.
C2. The thumbnail is a button labelled "Preview photo of <combo name>" (keyboard and screen reader).
    Read-only users can preview too; Replace / Clear stay edit-only.
C3. No photo: no thumbnail (as today), so nothing to click. A URL that fails to load shows the modal's
    existing "could not load" state, never a blank box.
C4. The tag designer is unchanged (its "Preview combo" select stays as today).

## Examples (real codes, from the owner's screenshots and repo fixtures)

The dev database is not reachable from this cloud sandbox (crew contract: no shared DB), so the figures are
the owner's screenshots; the read-only SQL at the bottom lets crew confirm them on dev.

- **E1 SRTBF11416 (Bathroom Furniture combo, white), SP line, template "Bathroom Furniture SP".** Formatted
  by hand in the editor: codes, MIRROR, SHELF bold black; part names and dimensions grey (text colour).
  Stored: `<p><strong>SRTBF11416</strong> <span style="color: #6b7280">(CABINET)</span></p><p><span
  style="color: #6b7280">L400xW345xH390mm</span></p>...`. Prints the same on canvas, request preview and PDF,
  then "LP: RM 730" and the big "SP RM 459". Plain-text readers get `SRTBF11416 (CABINET)\nL400xW345xH390mm\n...`.
- **E2 same combo, LP line.** Offered: LP, LP & SP and still-unset templates (e.g. "Small Price Tag LP").
  Prints "RM 730" and the description; no SP block, no "LP"/"SP" word.
- **E3 combo "SRTBF11829 + SRTMCB8083-BL" (LP 2,715, SP 2,099), no templates linked.** SP line row shows
  "No SP template linked"; preview eye disabled; Submit refuses with that reason.
- **E4 template "Bathroom Furniture SP" on release day.** Price type unset, badge "Set price type", still
  offered on LP and SP lines. The owner sets it to SP; from then on LP lines stop offering it.
- **E5 SRTBF11829 + SRTMCB8083-BL combo photo.** Click the thumbnail -> the app's image preview opens the
  photo full size with zoom; Escape closes it.
- **E6 a ticket (existing screen).** The same editor now also has Colour, Highlight, Underline and alignment;
  a red sentence is saved and shown red on the ticket.

## Open question (v2)

- **Q1 Font face and size inside the description.** (a) not in the editor: face and base size come from the
  template layer, headings H1-H3 give the bigger sizes; (b) add Font size (and font) to the shared editor
  too. **Recommend (a)**: every combo on one template keeps the same layout and fits its box, and the
  owner's flyer uses one face with bold and colour, which (a) covers.

## Edge cases

- `<script>alert(1)</script>` posted straight to the API: stored as nothing; `<img src=x onerror=...>`:
  removed; `<span style="color: red; background: url(javascript:...)">x</span>`: keeps only a valid colour
  value; `<a href="javascript:...">x</a>`: stored `<a>x</a>`, prints "x".
- Typed `<b>` in the editor is text (tiptap escapes it) and prints as `<b>`.
- Nested lists: indent per level, numbering restarts per list.
- Empty editor: stored NULL (the engine returns "" for an empty doc, `rich-text-editor.tsx:559`).
- 5000 character limit as today, counted on the stored (sanitised) value.
- White text on the white tag: allowed, visible in the live preview before saving.

## Crew read-only check on dev (optional)

```sql
SELECT t.name, t.published_version_id IS NOT NULL AS published
FROM dealer_kit.tag_template t ORDER BY t.name;
SELECT c.name, c.list_price, c.sell_price, c.description, c.image_attachment_id IS NOT NULL AS has_photo
FROM product_combos c JOIN products p ON p.id = c.host_product_id
WHERE p.product_code IN ('SRTBF11416','SRTBF11415','SRTBF11829');
```

## Track

Full track: migration (`tag_template.price_type`; `default_for` on the two link tables replacing the
`is_default` unique index), shared-engine change (8 screens), all three renderers. **security-reviewer is
mandatory**: stored HTML from several write paths, the allow-list sanitiser (style values included), the
no-innerHTML render on the public print page (`app/(public)/c/print/...`), and merge fields inside rich text.
