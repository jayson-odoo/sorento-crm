# CARD: price tag LP/SP per item, mixed request, per-item preview, AI extract of pasted lists (PRICETAG-LPSP, 4 Nov)

Behaviour card. Read of `origin/main` b272401f. Rulings that apply: 2 Nov (self-approve + edit,
1..n templates per product, Cabana has no selling price), 28 Oct (semantic extraction, no regex or
word lists; codes resolve through the existing resolver, never silent fuzzy matching), 1 Nov (live
minimum price alerts, "minimum price" wording).

## What exists today (measured)

- **LP or SP is a REQUEST fact, not a line fact.** `price_tag_requests.price_mode` is `list` |
  `selling` (`app/models/price_tag.py:107`); every line's `show_promo_price` is re-derived from it
  on save (`app/services/price_tag_request_service.py:525`, `:1150`). The form shows one
  `PriceModeToggle` (`components/dealer-kit/PriceModeToggle.tsx`). So a mixed LP+SP list today is
  two requests.
- **The line already stores a per-line flag** (`show_promo_price`, `price_tag.py:215`), and a line
  already carries its own `promotion_id` and `manual_sell_price` (`:222-228`). The renderer
  reads the per-line flag, not the header (`lib/dealer-kit/product-block.ts:139`, `:582`;
  `lib/dealer-kit/request-tags.ts:150`). Mixed rendering needs no renderer change; only how the
  flag is set changes.
- **Why LP and SP need two templates today.** A template prints a price three ways:
  a `price_badge` layer (`list_only` = LP; `promo` = struck LP + SP, and it already falls back to
  plain LP when the line is not on SP, `lib/dealer-kit/price-badge.ts:183-233`), or a TEXT layer
  bound to `list_price` or `sell_price` (`product-block.ts:366-372`). A text layer bound to
  `sell_price` prints NOTHING on an LP line, and one bound to `list_price` prints LP on an SP
  line. A small tag that prints a bare figure (no badge) is therefore hard-wired to one of them.
- **Preview exists, as one sheet.** `components/dealer-kit/PriceTagLivePreview.tsx` (from #2100)
  draws every line's tag with the line's template through `DesignViewer`, the proof's renderer,
  as ONE sheet. There is no per-line thumbnail.
- **Paste already reaches the AI extract.** The shared `components/common/ai-extract/AIExtractDialog.tsx:188-215`
  turns a clipboard text paste into a `.txt` upload; `app/services/ai_extract/extract_service.py`
  reads it. For `portal.price_tag_request` the entry shape is `{product_code, product_name, notes}`
  and rule (9) of the form's prompt forbids prices (`extract_service.py:990-1002`,
  `app/services/ai_prompt_registry.py:1174-1193`). Codes resolve through `_resolve_product_codes`
  (the one resolver, did-you-mean suggestions on a miss, #1867).
- **Minimum price** exists only in project pricing: `app/services/project_pricing_service.py:176`
  `resolve_floor(product, list_price)` (works without a series), shown as "Minimum price RM x"
  (`QuotationLineFlags.tsx:131-147`).
- **No selling price brands** (Cabana): `pricing.py:182` `_no_selling_price_product_ids` already
  keeps their promotions out of SP pricing (#2104).

## Rules (proposed)

R1. **One template, price slot follows the line.** Two new slot bindings a template can use:
    `price` ("Price, LP or SP": the line's SP on an SP line, its LP on an LP line) and
    `price_label` ("LP" or "SP"). Same `resolveSlotText` branch as `list_price`/`sell_price`, so
    the canvas and the PDF cannot disagree. The `promo` price badge keeps working as it does. No
    template is migrated automatically; existing LP and SP templates keep printing as before
    (Q1).
R2. **Price type per line, default from the request.** New column
    `price_tag_request_lines.price_type` (`list` | `selling`). The header toggle becomes "Default
    price" and fills NEW lines; each line row has its own LP/SP toggle that overrides it.
    `show_promo_price` is derived from the LINE's type (plus basis, as today) instead of the
    header. Existing lines are backfilled from their request's `price_mode`. Changing the
    default does not rewrite lines already set (Q2).
    A product of a no-selling-price brand (Cabana) is forced to LP: the SP toggle is disabled with
    a hint "No selling price for this brand.", and an SP sent by the API is stored as LP.
R3. **Per-item preview.** The Preview section shows one thumbnail per line (same
    `buildRequestSheet` + `DesignViewer`, one tag per page), labelled with the code and LP/SP;
    a click opens the existing lightbox at full size. The whole-sheet PDF stays where it is. A line
    with no template keeps the existing "No tag template yet for <code>." message in its tile.
R4. **Paste list.** The AI extract on the price tag form returns, per entry: `product_code`, the
    colour/finish suffix kept as part of the code, `price_type` (from a section header such as "LP"
    / "SP" or an inline "SP Rm599"; absent = request default), `typed_list_price`,
    `typed_sell_price`, and `set_codes` (the other codes joined with "+"). The model reads the
    structure; no regex or word list on our side (28 Oct). Rule (9)'s "no prices" is narrowed to
    "no quantities". Codes go through the existing resolver; a miss shows its did-you-mean list
    in the dialog for the user to pick or drop, never a silent fuzzy match.
R5. **Typed prices.** A typed SP on an SP line becomes the line's `manual_sell_price` (prints),
    with "System SP RM x" shown when it differs. A typed LP never prints (LP is master data); a
    difference shows "Typed LP RM x, system LP RM y" on the line. A stray second price on one
    entry (example E1, set 3) is shown in the line's remarks, not used (Q4).
R6. **Minimum price alert.** A selling price below `resolve_floor` shows the pill "Below the
    minimum price RM x" on the line, live, non-blocking (Q5).
R7. Self-approval (#2101): nothing changes in the approve flow; the per-line type is part of
    what the salesperson previews and approves.

## Combos (owner follow-up, 4 Nov)

What exists (measured):
- **Combo entity: yes.** `product_combos` (`app/models/product_combo.py:44-95`): one package on
  one HOST product, with parts (`product_combo_parts`, fixed or choice groups, upgrades with a
  top-up, `:97-135`), its own image (`:68`) and, since PRICETAG-COMBO, its own `description`,
  `free_items`, `list_price`, `sell_price` (`:73-76`). A request line already names one
  (`price_tag_request_lines.combo_id`, `app/models/price_tag.py:229-237`).
- Not the same thing: `product_sets` (`app/models/product_set.py:47`, a stock set with a
  `set_code`, members and a list price override) is what project quotations quote
  (`app/services/project_quotation_service.py:574-587`); a price tag line can be a set line
  (`line_type = product_set`). The chatbot business lane has no combo or set expansion
  (`app/services/chatbot/lanes/business/fetch.py`: no match).
- **Template link to a combo: no.** `dealer_kit.product_tag_template` links product x
  template only (`app/models/dealer_kit.py:812-830`). A combo line takes its HOST product's
  links: `_with_templates` picks from `published_links(line.product_id)`
  (`app/services/dealer_kit/product_tag_template_service.py:586-592`); combo_id plays no part.

What a combo tag prints today, tied to the SRTBF host:
- **Price:** the combo's own `list_price` / `sell_price` when set, else the summed parts
  (`app/services/dealer_kit/pricing.py:601-602`, `combo_prices` `:681-726`;
  `tag_data_service.py:897-901`). So "LP RM2155 / SP RM1729" prints only if it is stored on the
  combo (or typed as the line's manual SP).
- **Description:** the `combo_description` slot prints the combo's description, and when that
  is blank falls back to the HOST product's `price_tag_description`
  (`lib/dealer-kit/product-block.ts:324-330`): the BF cabinet's own text, wrong for a combo.
  `combo_name` falls back to the host code (`:319-323`).
- **Template:** whatever the BF product is linked to, so the BF sold alone and every BF combo
  share one template list: a combo layout is offered for the bare BF, and the bare layout for
  the combo.

Real examples (the 4 "+" lines of the owner's paste; whether each is a stored combo is a dev
data question, see the data request below):
- C1 `SRTBF11850 + SRTMCB8083-BL + SRTWT6204-MBL`, LP 2155 / SP 1729.
- C2 `SRTBF11839 + SRTWT5904 + SRTMCB8081-WH`, LP 2679 / SP 2149.
- C3 `SRTBF11840 + SRTWT8301-GMB + SRTMCB8083-BL`, LP 2911 / SP 2299 (plus a stray LP 2149).
- C4 `SRTBF11851 + SRTWT6201 + SRTMCB8081-WH`, LP 1864 / SP 1499.

Under (a): the extract matches a "+" line to the host's stored combo whose fixed parts are
exactly the listed codes -> a combo line (combo template, combo text, combo LP/SP; a typed SP
that differs is handled by R5). No stored combo matches -> a host line with those parts and the
typed SP as its manual price, and the dialog says "No combo with these parts on SRTBF11850."
so marketing can create one. New: `dealer_kit.combo_tag_template` (combo x template, same
shape and rules as the product link), edited on the combo modal where the combo's prices are
already edited. Template pick order for a combo line: combo links, else host product links.

## Examples

Dev data is not reachable from this cloud sandbox (crew rule: no shared DB). E1 is the owner's
message; E2 and E3 are earlier real requests named in this repo's plans; crew, please attach 2
masked real requests from dev data (crew-data-request) so the gold set reaches 8.

E1. The owner's 4 Nov paste (outlet name replaced): 30 lines under "LP" (`Srtsh2626 GY`,
    `SRTSS3240`, `Srtw1200 BL`...) -> 30 LP lines; then "SP": 4 sets
    (`Srtbf11850 +srtmcb8083 BL + srtwt6204 MBL  LP rm2155 SP RM1729`) -> 4 SP lines, each one tag
    with host `SRTBF11850` and two parts, typed SP 1729 as manual price, typed LP 2155 checked
    against the system; 8 SP singles (`Srtwc8518 SH SP Rm499`) with typed SP;
    `Srtwc8152 (6,8,10,P) SP Rm729` -> one line per variant only if each resolves, else one
    unresolved row with the variants listed; final "LP" section -> 5 LP lines.
E2. PT-202609-0004 (15 Sep, `PLAN-price-tag-ai-extract-resolver.md`): a 13-line sales order
    photo; no price type written -> all 13 take the request default.
E3. The 16 Sep paste of 21 bare product codes (`ai_prompt_registry.py:1178`): no header -> all
    default; proves rule (8) still forces `products`.
E4. A Cabana product under an "SP" header -> LP line, hint shown, no error.
E5. `Srtwc8066 S UF SP Rm599` where the system SP is RM 649 -> SP line printing RM 599 (typed),
    "System SP RM 649" shown; if RM 599 is below the floor, the minimum price pill shows too.

## Edge cases

- Set with its own price: one tag, typed SP is the set's manual price (R5).
- Code not found: row stays in the extract dialog as unresolved with suggestions; not added.
- Colour variant not in the catalogue (`Srtsh2626 GRY` when only `GY` exists): a resolver miss
  with `SRTSH2626-GY` offered as a suggestion; never auto-picked.
- Duplicate lines (`Srtss5726` and `Srtss5726 GM` are different codes; a true duplicate is the
  same resolved product twice): merged into one line, since `uq_ptag_line_request_product`
  allows one line per product per request; if the two ask for different price types, the
  later one wins and the dialog says "listed twice, kept as SP".
- Typed price below the minimum price: pill, not a block (R6).
- A request saved before this lane: lines backfilled from `price_mode`; it prints exactly as
  before.
- LLM input: the paste is untrusted text; it only fills the extract schema, is length-capped
  (existing upload cap), and never reaches a tool or a prompt other than the extract one.

## Questions (at most 5)

Q1. Templates hard-wired to LP or SP today: (a) keep them as they are, add the `price` and
    `price_label` slots, marketing converts the small price tag template (and the new DIY one)
    once; (b) also auto-rewrite every existing `list_price`/`sell_price` text slot to `price`.
    Recommendation: (a). An auto-rewrite changes how every proof prints, and a template whose
    designer meant "always LP" would silently start printing SP.
Q2. The default price type: (a) per request ("Default price" toggle, today's header toggle,
    each line overridable); (b) per brand (set on the brand); (c) per user (last used).
    Recommendation: (a), plus the no-selling-price brand rule forcing LP, which already exists.
    A per-brand setting is new configuration with only Cabana as evidence, and Cabana is
    already covered.
Q3. Combos (owner follow-up, 4 Nov: "should we be able to tag the combo with the template?").
    See "Combos" below for the evidence. (a) the combo is its own price tag item: templates link
    to the COMBO (1..n, same rule as products: one = automatic, many = pick), the combo prints
    its own description and its own LP/SP, preview per combo line; a combo with no template link
    falls back to its host product's templates as today; (b) keep tying to the BF host
    product's templates and print the combo text and price on them (today's behaviour);
    (c) one tag per component. Recommendation: (a), confirming crew's lean: the combo price
    (LP RM2155 / SP RM1729) and the combo description already live on the combo row and already
    print; the only missing piece is the template link. (b) offers the combo layout on the bare
    BF too, and prints the BF's own description when the combo's is blank. (c) has no
    per-component price to print.
Q4. Which price prints when the typed one differs from the system: (a) typed SP prints (as the
    line's manual selling price) with the system SP shown beside it; LP always prints from the
    system and a typed LP difference is only flagged; (b) the system price always prints and
    typed prices are only flagged. Recommendation: (a): a typed SP is what the dealer agreed,
    and the manual selling price field exists for exactly this; LP is master data.
Q5. Minimum price on price tags: (a) live, non-blocking pill "Below the minimum price RM x"
    from the same floor rules quotations use (`resolve_floor`); (b) out of this lane.
    Recommendation: (a): one read of an existing service, and it matches the 1 Nov ruling.
