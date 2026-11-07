# Red test list: PRICETAG-COMBO-FORMAT

For the `tester` agent, Phase 2, written BEFORE any implementation. UAC:
`pricetag-combo-format-acceptance-criteria.md` (AC numbers below). Branch from main AFTER #2172 merges.
Postgres only (`tests/_pg_fixture.py`), seed your own chain (CI DB is empty). Each test names its AC.
"KILL" = a kill test: revert the named production line and the test must go red (reviewer runs these).

## Backend (pytest)

### `tests/test_tag_rich_text_sanitise.py` (NEW, unit, no DB): AC-5..AC-8, AC-11, AC-12
1. keeps each allowed element with its text (parametrised over `p br strong em s u code h1 h2 h3 ul ol li
   blockquote a span mark`). AC-5
2. `<span style="color: #6b7280">x</span>` kept; `#abc`, `rgb(1, 2, 3)` kept; `color: red`,
   `color: #12345g`, `color: rgb(1,2)`, `color: url(javascript:alert(1))`, `color: expression(x)` -> style
   removed, text kept. AC-6
3. `background-color` same rules; `text-align: center` kept on `p`, removed on `span`; `text-align: justify`
   removed; `font-size`, `position`, `font-family` declarations removed. AC-6
4. attributes `href`, `class`, `id`, `onclick`, `onmouseover`, `data-x`, `target` all removed, including on
   `a`. AC-6
5. `<script>alert(1)</script>x` -> `x`; same for `style`, `iframe`, `object`, `embed` (content gone). AC-7
6. `<img src=x onerror=alert(1)>` -> ``; `<div>a</div>` -> `a`; `<svg><text>t</text></svg>` -> `t`;
   `<table><tr><td>c</td></tr></table>` -> `c`. AC-7
7. `&lt;b&gt;` stays escaped; `<!-- c -->` and `<!DOCTYPE html>` dropped; unclosed `<strong>a` closes. AC-8
8. idempotence over a corpus of 20 inputs (all of the above + E1). AC-8
9. mixed-case tags / attributes (`<SCRIPT>`, `ONERROR=`, `StYlE=`) handled the same. AC-6, AC-7
10. plain text (no leading allowed block tag) returned unchanged by `is_rich()` false path. AC-11
11. `plain_text()` of E1 HTML == E1 lines joined by `\n`; lists -> "• " / "1. " with numbering restarting
    per list; nested list indents with two spaces; plain input unchanged; `None` -> `None`. AC-12
KILL: remove the attribute filter -> 4 red; remove the style-value regex -> 2 red; remove the content-drop set
-> 5 red.

### `tests/test_product_combo_rich_description.py` (NEW, API): AC-9, AC-10, AC-11
1. PATCH `/api/v1/master-data/product-combos/{id}` with E1 HTML stores it byte-equal after sanitise; GET
   returns it. AC-9
2. PATCH with `<p>a<img src=x onerror=alert(1)></p>` stores `<p>a</p>`. AC-9
3. combo create (POST) sanitises the same way. AC-9
4. `<p></p>` and `"  "` store NULL. AC-10
5. 5001-character value AFTER sanitising -> 422 (message unchanged from today); a 6000-character value that
   sanitises to under 5000 (stripped attributes) -> 200. AC-10
6. legacy plain text "SRTBF11416 (CABINET)\nL400xW345xH390mm" stored unchanged. AC-11
KILL: bypass the sanitiser in `product_combo_service` update -> 2 red.

### `tests/test_product_price_tag_description_rich.py` (NEW, API): AC-9, AC-10
1. product update with `price_tag_description` HTML containing `<script>` stores it without the script. AC-9
2. merge-field text `{{spec.width}}` inside `<strong>` survives sanitising unchanged. AC-9

### `tests/test_import_product_combos.py` (EXTEND): AC-9, AC-12
1. a seed whose `combo_description` holds `<p onclick=x>a</p>` stores `<p>a</p>` on `--apply`. AC-9
2. an existing combo with `<p><strong>SRTBF11416</strong> (CABINET)</p>` vs seed text
   "SRTBF11416 (CABINET)" reports "matches", not "differs". AC-12

### `tests/test_migration_ptag_combo_format.py` (NEW, migration): AC-26, AC-30
1. upgrade: `tag_template.price_type` exists, nullable, CHECK refuses `'x'`; existing rows NULL. AC-26
2. upgrade: a product link with `is_default = true` -> `default_list` and `default_selling` both true;
   others false; same for a combo link; `is_default` column gone. AC-30
3. partial unique indexes: a second `default_list = true` row for the same product -> IntegrityError; same
   for `default_selling`; same on the combo table. AC-30
4. downgrade restores `is_default` (selling flag first, else list), drops the new columns; upgrade again is
   clean. AC-26, AC-30
5. single head, revision id <= 32 chars. AC-26

### `tests/test_tag_template_price_type.py` (NEW, API): AC-27, AC-29
1. POST / PUT `/api/v1/dealer-kit/tag-templates` with `price_type` in (list, selling, both, null) persists;
   `"lp"` -> 422. AC-27
2. publish does not change `price_type`; GET of a published template returns it. AC-27
3. list filter `price_type=unset` returns only NULL rows; `price_type=selling` only selling. AC-29

### `tests/test_tag_template_links_default_per_type.py` (NEW, API): AC-31
1. PUT `/dealer-kit/products/{id}/tag-templates` with `default_list_template_id` = LP template and
   `default_selling_template_id` = SP template stores both; GET returns `default_list` / `default_selling`
   and `price_type` per item. AC-31
2. LP-only template as `default_selling_template_id` -> 422 `TEMPLATE_PRICE_TYPE_MISMATCH`. AC-31
3. default id not among the linked ids -> 422 (unchanged code). AC-31
4. same three on `/dealer-kit/combos/{id}/tag-templates`; a combo whose host is in another company -> 404
   (unchanged). AC-31
5. a lone `both` link is the default for LP and SP; a lone `list` link is the LP default only. AC-31
KILL: drop the type-fit check -> 2 red.

### `tests/test_price_tag_line_template_price_type.py` (NEW): AC-33..AC-39
1. product with links {LP, SP, both, unset}: `line_links` for an LP line -> {LP, both, unset}; SP line ->
   {SP, both, unset}. Portal lookup with the line's type answers the same. AC-33
2. save an SP line with no pick -> SP default; with a sent LP-only pick -> 422
   `TEMPLATE_PRICE_TYPE_MISMATCH`. AC-34
3. SP line on a combo whose only link is LP -> submit 422 `NO_TEMPLATE_FOR_PRICE_TYPE`, message
   "<combo>: No SP template linked"; LP mirror case. AC-36
4. an existing saved line on template T (LP); then T's type set to SP: resolve/print still uses T; the
   line is not rewritten; editing that line's price type re-filters. AC-37
5. approved tag with pinned data keeps its template and pinned data after the type change. AC-37
6. Cabana product (no-selling-price brand) SP line with typed SP: SP templates offered. AC-38
7. all templates NULL: for 4 seeded shapes (product, product with 2 links, combo with links, combo without
   links -> host's), the offered set equals main's behaviour (assert against a fixture of expected ids).
   AC-39
KILL: remove the price-type filter in `line_links` -> 1 red; make NULL count as `list` only -> 7 red.

## Frontend (vitest)

### `components/ui/rich-text-editor.toolbar.test.tsx` (NEW): AC-1, AC-2
1. renders buttons with aria-labels "Text colour", "Highlight", "Underline", "Align left", "Align centre",
   "Align right" plus the existing ones. AC-1
2. select text, pick swatch #6B7280 -> onChange HTML contains `<span style="color: #6b7280">`; "Remove
   colour" -> no span. AC-2
3. Highlight -> `background-color`; Align centre -> `text-align: center` on the `<p>`. AC-2
4. Underline toggles `<u>`. AC-2

### existing editor suites (RUN, unchanged): AC-4
`components/ui/rich-text-editor.labels.test.tsx`, ticket / email template / quotation editor tests: green
with no snapshot change for inputs that do not use the new buttons.

### `components/common/ColorPicker.test.tsx` (MOVED with the component): AC-3
existing designer colour tests pass against the new path; a grep test asserts no file imports
`tag-templates/components/ColorPicker`.

### `lib/dealer-kit/rich-text.test.ts` (NEW): AC-13, AC-14, AC-20
1. E1 HTML -> 12 paragraph blocks; bold runs exactly SRTBF11416, SRTWB248, MIRROR, SHELF, SRTWT5837,
   SRTW2600; grey runs on the dimension lines. AC-13
2. h1 / h2 / h3 -> bold with factors 1.4 / 1.2 / 1.1. AC-13
3. `<ul><li>a</li><li>b</li></ul><ol><li>c</li></ol><ol><li>d</li></ol>` -> "•", "•", "1.", "1."; nested
   list level 2. AC-13
4. alignment per block; unset alignment = null (layer decides). AC-13
5. plain text "a\nb" -> 2 paragraphs, no marks. AC-13
6. `color: javascript:x` or `color: red;}` in a span -> run colour null. AC-14
7. a `<img onerror>` string inside text -> literal text run; parser does not touch `innerHTML` (spy on
   `Element.prototype.innerHTML` setter: never called). AC-14
8. `<a>` -> its text; `<div>x</div>` (old data) -> text x. AC-20

### `lib/dealer-kit/text-lines.runs.test.ts` (NEW): AC-15
1. "**SRTBF11416** (CABINET)" equivalent runs in a box that fits only the bold word on line 1 breaks after it
   with the bold face measured (a version measuring everything regular breaks elsewhere: assert the break).
2. same input via the canvas caller and the print caller -> equal line lists.
KILL: measure all runs with the regular face -> 1 red.

### `app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer.rich-text.test.tsx` (NEW): AC-16
1. E1: number of Konva Text nodes == number of runs; bold runs have `fontStyle` bold; grey runs `fill`
   #6b7280; family and base size equal the layer's.
2. h1 run font size == layer size * 1.4.

### `app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer.rich-text.test.tsx` (NEW): AC-17
1. E1 renders bold spans for the six bold words and grey spans for dimensions.
2. a description `"<img src=x onerror=alert(1)>"` (as text) renders as visible text; no `img` element.
3. static check: the file contains no `dangerouslySetInnerHTML` / `innerHTML`.

### `lib/dealer-kit/rich-text.parity.test.ts` (NEW): AC-18
canvas line model == print line model (text + face per run) for E1 and for a description using every
toolbar item.

### `lib/dealer-kit/product-block.merge-rich.test.ts` (NEW): AC-19
spec value `"<b>x</b>"` substituted into `<p>{{spec.width}}</p>` -> a single text run `<b>x</b>`.
KILL: substitute before parsing -> red.

### `.../products/[id]/components/ProductCombosSection.rich.test.tsx` (NEW): AC-21, AC-23, AC-24, AC-40..AC-42
1. editor present for an editor user; blur calls the combo PATCH with HTML; failure reverts. AC-21
2. live preview renders via `DesignViewer` with the default template; typing updates it; no default ->
   "No price tag template linked". AC-23
3. read-only user: formatted output, no `&lt;strong&gt;` / raw tag text visible. AC-24
4. thumbnail is a button named "Preview photo of <combo name>"; click -> `AttachmentPreviewModal` open with
   the item `{id: attachment_id, name, url}`; Enter opens; Escape closes. AC-40
5. read-only user can open it; no Replace / Clear. AC-41
6. combo without image: no button. AC-42

### `.../products/[id]/components/ProductSpecificationsTab.rich.test.tsx` (NEW): AC-22
merge field inserted at the cursor in the rich editor via `onEditorReady`.

### `app/(protected)/dealer-kit/tag-templates/components/TagTemplateDialog.priceType.test.tsx` (NEW): AC-28
toggle LP / SP / LP & SP beside Family; save sends `price_type`.

### tag template list test (NEW, beside the list page): AC-29
"Set price type" badge on NULL rows; "Price type: Not set" filter sends `price_type=unset`.

### `.../products/[id]/components/ComboTemplatesPicker.priceType.test.tsx` (NEW) and
### `ProductTagTemplatesSection.priceType.test.tsx` (NEW): AC-32
chips show type labels; "default LP" / "default SP" set independently; the SP-default control does not
offer an LP-only template.

### `components/dealer-kit/PriceTagLinesTable.priceTypeTemplates.test.tsx` (NEW): AC-35, AC-36
1. LP line's template select lists only LP / LP & SP / unset; flipping to SP switches to the SP default;
   a `both` pick is kept. AC-35
2. no SP-capable template: "No SP template linked" pill, eye disabled, Submit disabled with the reason.
   AC-36

### designer unchanged: AC-43
existing `TagCanvasEditor` "Preview combo" tests run green.

## Browser (crew pass, agent-browser, after green)

E1 on the combo page (editor + live preview), the request preview and the print page look identical;
template price type set by hand; SP line with no SP template refused; combo photo opens full size; 375 and
1280 px. AC-25.
