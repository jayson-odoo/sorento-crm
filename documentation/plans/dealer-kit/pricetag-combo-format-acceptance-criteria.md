# UAC: PRICETAG-COMBO-FORMAT (rich description, hand-picked LP/SP template type, combo photo preview)

Plan: `PLAN-pricetag-combo-format-05nov.md`. Card: `CARD-pricetag-combo-format-05nov.md` (v2). Mock (owner
approved v2, 5 Nov ~10:25 MYT): `pricetag-combo-format-mock.html`. Font face / size: card Q1 (a), face and
base size from the template layer, headings for bigger sizes (crew, 5 Nov).

Each AC names its test kind; the red test list is `pricetag-combo-format-test-list.md`. Real case: combo
SRTBF11416 (LP 730 / SP 459) and combo "SRTBF11829 + SRTMCB8083-BL" (LP 2,715 / SP 2,099). Tests seed their
own chain (CI database has no data); codes are reused only as labels.

## S1. Shared rich text engine, completed (A1)

- AC-1. `RichTextEditor` shows Text colour, Highlight, Underline, Align left / centre / right buttons, each
  with an aria-label, in addition to today's buttons (Bold, Italic, Strikethrough, Inline code, H1-H3,
  Bullet list, Numbered list, Blockquote, Link, Undo, Redo). (vitest)
- AC-2. Picking a colour in the Text colour popover on selected text emits HTML with
  `<span style="color: #6b7280">`; "Remove colour" removes it. Highlight emits `background-color`.
  Align centre emits `style="text-align: center"` on the paragraph. (vitest)
- AC-3. The colour popover is the ONE colour control: `components/common/ColorPicker.tsx`; the tag designer
  imports it from there and the old path no longer exists. Designer colour tests stay green. (vitest + grep)
- AC-4. Existing screens keep working: a ticket / email template / quotation editor test that saved HTML
  before still saves the same HTML for the same input (no new markup without a new button press). (vitest,
  existing suites)

## S2. Storage: server-side allow-list (A3, A7, A9)

- AC-5. `sanitise_tag_html()` keeps `p br strong em s u code h1 h2 h3 ul ol li blockquote a span mark` and
  their text. (pytest unit)
- AC-6. Drops every attribute except: `style` with `color` / `background-color` whose value is `#rgb`,
  `#rrggbb` or `rgb(r, g, b)`; `style` with `text-align: left|center|right` on `p h1 h2 h3 li`. Any other
  declaration, value (`url(...)`, `expression(...)`, named colours with junk) or attribute (`href`, `class`,
  `on*`, `data-*`, `id`) is removed. (pytest unit, parametrised)
- AC-7. `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>` are dropped WITH their content; any other
  unknown tag (`<img>`, `<div>`, `<table>`, `<svg>`) is removed and its text kept, escaped. (pytest unit)
- AC-8. Text is escaped on output: `&lt;b&gt;` in input stays `&lt;b&gt;` (never becomes a tag); comments
  and `<!DOCTYPE>` are dropped. Output is idempotent: `sanitise(sanitise(x)) == sanitise(x)`. (pytest unit)
- AC-9. Every write path stores the sanitised value: PATCH `/master-data/product-combos/{id}` description,
  product update `price_tag_description`, combo create, the combo importer (`import_product_combos.py`),
  and any AI extract that writes a description. A raw `<img src=x onerror=alert(1)>` sent to each is stored
  without the `img`. (pytest API)
- AC-10. Empty markup (`<p></p>`, whitespace) stores NULL. The 5000-character limit is checked on the
  sanitised value (422 above it, unchanged message). (pytest API)
- AC-11. Legacy plain text (no leading allowed block tag) is stored as sent (plain text stays plain until
  edited in the editor) and is treated as plain text by every reader. (pytest unit + API)
- AC-12. `plain_text()` returns text with line breaks per block, "• " per bullet, "1. " per numbered item,
  no markup; plain-text input returns unchanged. Used by: the combo importer's compare/report (a combo whose
  only difference is formatting reports "matches"), and every API/MCP/chatbot reader of
  `product_combos.description` / `products.price_tag_description` found at build (`grep` list recorded in
  the plan). (pytest unit + importer test)

## S3. One parser, three renderers (A4, A5, A6, A9)

- AC-13. `lib/dealer-kit/rich-text.ts` `parseRichText(value)` returns blocks of runs for every allowed
  element: marks bold / italic / underline / strike / code / color / highlight; blocks paragraph, h1-h3
  (bold, size factor 1.4 / 1.2 / 1.1), list item (bullet "•" or number, nesting level, numbering restarts
  per list), quote (indent), alignment. Plain text -> one paragraph per line. (vitest)
- AC-14. The parser re-validates colours (hex / rgb only); an invalid colour run draws in the layer colour.
  It never uses `innerHTML` (parses with `DOMParser` into a model). (vitest)
- AC-15. `textLayerLines` with runs: a line that mixes bold and normal text breaks at the same word as
  measured in each run's own face; the result is identical for canvas and print callers (one function).
  (vitest)
- AC-16. Canvas: `KonvaTagLayer` `TextContent` draws one text node per run with the run's face, colour,
  decoration; a heading run uses the layer size times its factor. Font family and base size are the
  layer's (no face/size from the description). (vitest)
- AC-17. Print/PDF: `TagSheetRenderer` renders the same model as React `<span>`s; the rendered DOM for the
  SRTBF11416 description contains `<strong>`-equivalent bold spans for SRTBF11416, SRTWB248, MIRROR, SHELF,
  SRTWT5837, SRTW2600 and grey spans for the dimensions; no element in the print tree is created from
  `innerHTML` / `dangerouslySetInnerHTML` (static check on the file + DOM assertion that a
  `<img onerror>` string in the description renders as text). (vitest)
- AC-18. Parity: for the same tag data, the canvas line list and the print line list (text + face per run)
  are equal for E1 and for a description using every toolbar item. (vitest parity test)
- AC-19. Merge fields in `price_tag_description` resolve on text runs: a spec value `"<b>x</b>"` prints as
  the literal text `<b>x</b>`. (vitest)
- AC-20. A link prints its text only; an unknown leftover tag (from old data) prints its text. (vitest)

## S4. Editors in the product page (A2)

- AC-21. The combo Description uses `RichTextEditor`; blur saves the HTML through the existing combo PATCH;
  a failed save reverts (unchanged behaviour). (vitest)
- AC-22. The product's price tag description (`PriceTagDescriptionBlock`) uses `RichTextEditor`; its
  insert-merge-field action inserts at the cursor through `onEditorReady`. (vitest)
- AC-23. Beside the combo editor, a live tag preview renders the combo with its default template through
  `DesignViewer`; editing (before blur) updates the preview. No default template: the preview says
  "No price tag template linked". (vitest)
- AC-24. Read-only users see the description FORMATTED (rendered from the parser model), never raw HTML
  tags. (vitest)
- AC-25. Usable and not clipped at 375 px and 1280 px (toolbar wraps). (browser)

## S5. Template price type, hand-picked (B1, B2)

- AC-26. Migration adds nullable `dealer_kit.tag_template.price_type` with CHECK `('list','selling','both')`;
  existing rows are NULL. Downgrade drops it. Head id <= 32 chars, single head. (pytest migration)
- AC-27. Template create / PUT accept `price_type` (`list` | `selling` | `both` | null); anything else 422.
  GET returns it. Publish copies nothing new (price type is a template fact, not a version fact). (pytest API)
- AC-28. The template dialog shows "Price type" LP / SP / LP & SP beside Family; saving persists it.
  (vitest)
- AC-29. The template list shows a "Set price type" badge on a template with NULL price type and filters
  by price type including "Not set". (vitest + pytest list filter)

## S6. Links: one default LP and one default SP (B3)

- AC-30. Migration replaces `is_default` on `product_tag_template` and `combo_tag_template` with two
  booleans `default_list` and `default_selling` (NOT NULL, default false), each with a partial unique index
  per owner (`product_id` / `combo_id` WHERE flag). Backfill: an `is_default = true` row gets both flags true
  (today's default stays the default for LP and SP lines). The old `is_default` column and index are
  dropped. Downgrade: `is_default = default_selling`, or `default_list` where the owner has no
  `default_selling` row. Head id <= 32 chars, single head. (pytest migration)
- AC-31. PUT product / combo templates takes `default_list_template_id` and `default_selling_template_id`;
  each must be among the linked ids AND fit its type (an LP-only template cannot be the SP default: 422
  `TEMPLATE_PRICE_TYPE_MISMATCH`). GET returns `default_list`, `default_selling`, `price_type` per item.
  A lone fitting link counts as the default for its type(s). (pytest API)
- AC-32. Picker UI: each chip shows LP / SP / LP & SP / Not set and "default LP" / "default SP" stars;
  setting a default is per type. (vitest)

## S7. Request line offers only matching templates (B4, B5, B6, B7, B8)

- AC-33. `line_links` / portal lookup for an LP line returns templates with price_type in
  (list, both, NULL); for an SP line (selling, both, NULL). (pytest)
- AC-34. `pick_template` on save: a sent pick that does not match the line's price type is refused 422
  `TEMPLATE_PRICE_TYPE_MISMATCH`; no pick -> that type's default -> lone fitting link. (pytest)
- AC-35. Flipping a line LP -> SP in the form switches its template to the SP default; a pick that fits both
  is kept. (vitest)
- AC-36. An SP line whose item has no SP-capable template: row shows "No SP template linked", the row's
  preview eye is disabled, Submit and Approve are refused with reason
  "<item>: No SP template linked" (422 `NO_TEMPLATE_FOR_PRICE_TYPE` server-side, same text FE). Same for LP
  ("No LP template linked"). (pytest + vitest)
- AC-37. Existing request lines whose stored template no longer matches (after the owner sets a type) are
  NOT rewritten and still print; approved tags keep their pinned data. Only a new pick or an edit of that
  line is filtered. (pytest)
- AC-38. A no-selling-price brand (Cabana) SP line with a typed SP is offered SP templates like any item.
  (pytest)
- AC-39. Release-day compatibility: with every template NULL, every line is offered exactly the templates
  it is offered on main today. (pytest, kill test against the filter)

## S8. Combo photo preview (C1-C4)

- AC-40. In the Combos section, the combo photo thumbnail is a button labelled
  "Preview photo of <combo name>"; click or Enter opens `AttachmentPreviewModal` with
  `items=[{id: image.attachment_id, name: <combo name>, url: image.url}]`; Escape closes it. (vitest)
- AC-41. Read-only users can open it; Replace / Clear stay edit-only. (vitest)
- AC-42. No photo: no thumbnail, no button (unchanged). (vitest)
- AC-43. The tag designer is unchanged: "Preview combo" select still present (existing test green).

## DoD

- Red tests first (tester), then green (coder); kill tests listed in the test list must go red when the
  named line is reverted.
- reviewer + security-reviewer (mandatory: stored HTML, style values, public print page, merge fields).
- Browser pass (crew): E1 on canvas, request preview and print page look identical; 375 / 1280.
- Owner hand test via `crew-handtest:`.
