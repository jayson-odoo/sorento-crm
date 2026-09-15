# UAC: price tag AI extract through the entity resolver; Add part only with a combo

Plan: PLAN-price-tag-ai-extract-resolver.md

## S1 One matcher

- AC-S1-1 `[BE]` An extracted `product_code` of `Srt6536 DIY` on a company holding active product
  `SRT6536-DIY` returns `product_code="SRT6536-DIY"`, `match="product"`, `product_id=<row id>`.
  Same for `srt384-6 diy` -> `SRT384-6-DIY` and `SRTKT74SS BL` -> `SRTKT74SS-BL` (parametrized
  over dash / space / case variants; the separator matrix
  `tests/test_entity_resolver_separator_matrix.py` is the reference).
- AC-S1-2 `[BE]` A code with no exact match keeps the raw text, `match=None`, both ids `None`.
- AC-S1-3 `[BE]` A code that matches a `ProductSet.set_code` returns `match="product_set"` and
  `product_set_id`.
- AC-S1-4 `[BE]` A product of another company is not matched (company scope of the portal token).
- AC-S1-5 `[BE]` `_canonical_product_code` no longer exists; the service imports and calls
  `resolve_references` (assert with a spy that it is called once per extract with the whole
  code list, `enable_prefix_fallback=False`, `enable_embedding_fallback=False`).
- AC-S1-6 `[FE]` The extract dialog shows "Matched product" / "Matched set" / "Not found" per row
  from the payload alone; `lookupTagItems` is not called during extract.
- AC-S1-7 `[FE]` Apply adds a line for every matched row (product or set) and toasts "Not found:
  ..." for the rest, unchanged from today.

## S2 Add part only with a combo

- AC-S2-1 `[FE]` A product line whose combos lookup returned an empty list shows no "Add part"
  search. Existing part rows on that line still render with Remove.
- AC-S2-2 `[FE]` A product line whose lookup returned one or more combos shows "Add part".
- AC-S2-3 `[FE]` Before the lookup answers, no "Add part" search (no flash).
- AC-S2-4 `[BE]` Create / replace lines with a non-empty `parts` on a product line whose product
  has no `ProductCombo` returns 422 naming the line index; the request is unchanged.
- AC-S2-5 `[BE]` The same payload on a product with a combo is accepted (regression).

## S3 One row when a line has one tag and no parts

- AC-S3-1 `[FE]` On the detail Lines tab a product line with one tag and no parts renders ONE
  `<tr>`: Type badge, code, name, qty, the tag's List Price, Sell Price (and override line),
  Remarks, tag status (Designed / No tag, plus Changed when the tag has a pending change) and
  the Review / Design buttons. No `1a` text anywhere on that row.
- AC-S3-2 `[FE]` A line with two tags renders the line row plus `1a` and `1b` tag rows, as today.
- AC-S3-3 `[FE]` A line with one tag and one or more parts renders the line row, the part rows
  and the `1a` tag row, as today.
- AC-S3-4 `[FE]` The Design button on a folded row opens the designer for that tag (same
  `openDesignerForTag(tag.id)`), and Review opens the change review for it.

## S4 Designer rail: one block per line when the line has one tag and no parts

- AC-S4-1 `[FE]` A line with one tag, no parts and no open group renders one block: code, name
  (when it differs from the code), `Qty <n> / <family> / LP <price>` (or SP / Override per the
  existing rules), the designed check, the open-pins count. No "1a" text. Clicking the block
  selects that tag (`onSelect(tag.id)`), and the block carries the selected highlight.
- AC-S4-2 `[FE]` "Use template for tag 1a" and the Review button (when the tag has a pending
  change) are on that block; no Remove button.
- AC-S4-3 `[FE]` A line with two tags renders the line block plus `1a` / `1b` tag rows, as today.
- AC-S4-4 `[FE]` A line with one tag and an open group keeps the tag row (the Split / Pick one
  controls live there).

## S5 Tag Size panel collapsible

- AC-S5-1 `[FE]` `TagSizeControl` renders collapsed by default: the "Tag Size" heading with the
  current size beside it (`95 x 44.5 mm`), and no preset select, W / H inputs or "Apply to all
  lines" button in the document.
- AC-S5-2 `[FE]` Clicking the heading opens it (select, inputs, buttons present); clicking again
  collapses it. The trigger is a button with `aria-expanded`.
- AC-S5-3 `[FE]` With `localStorage["dealer-kit.tag-size.open"] === "1"` it renders open; opening
  or closing writes the key. A throwing `localStorage` does not break the render (collapsed).
- AC-S5-4 `[FE]` Existing `TagSizeControl.test.tsx` cases that interact with the select or
  inputs open the panel first and still pass.

## Verification

- pytest: the two new BE files green; `tests/test_ai_extract_service.py` and
  `tests/test_price_tag_*` still green.
- vitest: the two touched FE spec files green.
- agent-browser on :3080: portal price tag form, paste the 13-line text from the owner's 15 Sep
  screenshot as a .txt, Extract with AI, expect >= 9 "Matched product" rows; after Apply, a line
  for `SRTWT8203` shows no "Add part" if it has no combo.
