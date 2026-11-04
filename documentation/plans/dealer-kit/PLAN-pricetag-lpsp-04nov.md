# PLAN: price tag LP/SP per item, mixed request, per-item preview, AI extract of pasted lists

**Lane:** PRICETAG-LPSP (PR #2158)
**Status:** Review done, hand test next (4 Nov). Owner answered all 6 (Q1 a, Q2 "Preferred Default" with
unset lines following it, Q3 a, Q4 = existing basis rule per line, Q5 b, Q6 = match stored combos only).
Reviewer re-check: all findings fixed, last kill-test gap closed; security READY; browser pass 1280/375
done (evidence-pricetag-lpsp/). Track: full LEAD track (size L, migration, LLM input surface).

Card: `CARD-pricetag-lpsp-04nov.md`. Mock: `pricetag-lpsp-mock.html`. UAC:
`pricetag-lpsp-acceptance-criteria.md`.

## Owner rulings (4 Nov, via crew)

- Q1 (a): keep the existing LP / SP templates; add the "Price (LP or SP)" and "Price label" slots.
  The owner edits templates himself; no conversion by us.
- Q2: the request toggle is the starting value for new lines, labelled "Preferred Default"; each
  line overridable.
- Q3 (a): templates link to combos too (1..n, like products).
- Q4: LP is NEVER typed (system / summed parts). SP may be typed only on a line with no promotion
  (or after the user unlinks it); otherwise SP = the promotion price. This is today's rule
  (`_validate_line_price_basis`, `price_tag_request_service.py:271-312`), kept, now judged per line.
- Q5 (b): no minimum price on tags. R6 dropped.
- Q6 (owner mock v2 notes): a "+" line must match an EXISTING stored combo. No match = an
  unmatched row like an unknown code; the user picks an existing combo or products in the row
  picker. Nothing creates a combo from the form (the salesperson cannot define combos).
- NEW: a product (and a combo) has a DEFAULT price tag template among its links, preselected on
  the line (the user can still change it).
- NEW: remove the hint "Add an item to see its tag before approving." under Approve
  (`PriceTagRequestForm.tsx:1300`).
- Mock notes: unmatched extract row has a manual product picker; "+" lines show as Combo; Cabana
  may go SP with a typed price (no system SP); per-row eye icon opens the tag in a lightbox; no
  extra hint texts (discontinued etc.), only what blocks Submit.

## Slices (one coder, commits on this branch)

### S1. Data (one migration `ptag_0014_lpsp`, down_revision = current head)
- `price_tag_request_lines.price_type VARCHAR(16) NULL`, CHECK in ('list','selling'); backfill
  `UPDATE ... SET price_type = r.price_mode FROM price_tag_requests r WHERE r.id = request_id`.
  Effective type = `line.price_type or request.price_mode`.
- `dealer_kit.product_tag_template.is_default BOOLEAN NOT NULL DEFAULT false`; partial unique
  index `(product_id) WHERE is_default`.
- New `dealer_kit.combo_tag_template (id uuid pk, combo_id FK product_combos CASCADE,
  template_id FK dealer_kit.tag_template CASCADE, is_default bool default false, created_by,
  created_at)`, unique (combo_id, template_id), partial unique (combo_id) WHERE is_default.

### S2. BE price type per line
- Schemas (`app/schemas/price_tag.py`): line create/update/revise + `TagPreviewLineInput` +
  line out gain `price_type: Optional[Literal['list','selling']] = None`.
- `_validate_line_price_basis(promotion_id, manual, price_type)`: same two refusals, judged
  against the LINE's effective type. Every caller passes the effective type.
- `show_promo_price = effective == 'selling' and basis != 'list'` everywhere it is derived
  (`price_tag_request_service.py:525`, `:1150`; `tag_data_service.py:716`, `:828`, `:838`,
  `:935`; `product_tag_template_service.py:545`).
- No-selling-price brand (Cabana): unchanged guard (no promotion SP); a typed manual SP is
  allowed on an SP line (already true: the guard only filters promotions). No hint text.

### S3. BE templates: default + combo links
- `set_product_templates(..., default_template_id=None)`: default must be one of the ids; PUT
  body `ProductTagTemplatesUpdate.default_template_id: Optional[str]`; item out gains
  `is_default`. A single link is implicitly the default.
- Combo links: `GET|PUT /dealer-kit/combos/{combo_id}/tag-templates` (same `_VIEW` / `_MANAGE`
  gates as the product routes, `app/api/v1/dealer_kit/tag_data.py`), combo scoped through its
  host product (`_scoped(Product)`), 404 for a foreign combo.
- Portal lookup `/lookups/product-tag-templates/{product_id}?combo_id=` : combo's published links
  when the combo has any (and hangs off that product), else the product's; each with `is_default`.
- Pick order (`line_template_id`, `_with_templates`, `require_line_templates`): sent pick if
  allowed -> the default -> the only link -> (preview only) first link. A line with 2+ links and
  a default no longer needs a pick at Submit.

### S4. (dropped: owner ruled no request-only combos)

### S5. BE extraction (LLM input surface)
- `portal.price_tag_request` entry shape: `{product_code, product_name, notes, price_type,
  typed_list_price, typed_sell_price, set_codes}`. Prompt rule (9) narrowed to "never quantities";
  new rule (10): a line under a header "LP"/"SP" (or carrying "LP rm.." / "SP rm..") takes that
  price type; `set_codes` lists the codes joined to the first by "+"; a second price of the same
  kind on one line goes to `notes`. Semantic, read by the model; no regex on our side.
- `_extract_products`: coerce `price_type` to 'list'|'selling'|None (anything else -> None);
  typed prices via `_coerce_float`, negative / >1e7 -> None; `set_codes` capped at 10 strings of
  <= 64 chars; each set code resolved through the SAME `_resolve_product_codes` batch; output
  `ExtractedProductLine` gains `price_type`, `typed_list_price`, `typed_sell_price`, `set_parts:
  [ExtractedProductSuggestion-like {product_id, product_code, product_name} | unresolved code]`,
  `combo_id` (a stored combo on the resolved host whose FIXED parts equal the resolved set
  parts exactly; else None, and the line's `match` is None so the dialog shows it unmatched)
  and `combo_name`.
- Typed LP is never applied (Q4); it is returned only so the dialog can flag a mismatch.

### S6. FE
- `lib/dealer-kit` slot bindings `price` ("Price (LP or SP)") and `price_label` ("Price label"):
  `price` = offer price when the line shows SP, else LP; `price_label` = 'SP' / 'LP'. Same
  `resolveSlotText` branch as `list_price`/`sell_price`; added to the editor's slot list.
- `PriceTagLinesTable`: per-line LP/SP toggle (same control as `PriceModeToggle`), default from
  the header for new lines; manual SP input enabled only when the line is SP and has no
  promotion; eye icon button ("Preview tag") per row opening that line's tag in
  the `DesignViewer` lightbox (`PriceTagLivePreview` per-line mode). Header toggle label:
  "Preferred Default".
- Template select preselects the default (product or combo).
- AI extract review (shared `AIExtractDialog`, price tag form only): Price (LP/SP) and Typed
  columns, Combo pill for matched set lines, manual picker (existing combo or product) on an
  unmatched row; apply writes `price_type`, `manual_sell_price` (typed SP, only when the line
  has no promotion) and `combo_id`.
- Product page templates section + `AddComboModal`: "Default" choice among linked templates;
  combo modal gains the templates field (`dealer_kit.tag_templates.manage` to edit).
- Remove the "Add an item to see its tag before approving." hint.

## Not in this lane
Minimum price (Q5 b). Template conversion (Q1, owner). Per-brand / per-user default (Q2).
Creating combos from the request form (Q6).
