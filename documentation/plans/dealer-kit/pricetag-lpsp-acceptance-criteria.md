# UAC: PRICETAG-LPSP (price type per line, default + combo templates, paste extraction)

Plan: `PLAN-pricetag-lpsp-04nov.md`. Each AC names its test.

## Price type per line (S2)
- AC-1. A request in List mode can carry an SP line: saving lines `[{A, price_type: list},
  {B, price_type: selling, manual_sell_price: 599}]` stores both types; B's `show_promo_price` is
  true, A's false. (pytest)
- AC-2. A line with no `price_type` takes the request's `price_mode` (stored explicitly on save).
  (pytest)
- AC-3. Manual SP on an LP line is refused 422 `INVALID_LINE_PRICE` even in a Selling-mode request;
  manual SP on an SP line of a List-mode request is accepted. (pytest)
- AC-4. Manual SP together with a promotion on the same line is refused (unchanged). (pytest)
- AC-5. Resolved tag data (`resolve_tags_live`) for a mixed request: the SP line has `sell_price`
  and `show_promo_price` true, the LP line `show_promo_price` false. Preview (`/lookups/tag-preview`
  unsaved lines) honours each line's `price_type`. (pytest)
- AC-6. Migration backfills `price_type` from `price_mode` for existing lines; downgrade drops the
  new columns/table. (pytest migration test)
- AC-7. A no-selling-price brand product on an SP line with a typed SP prints the typed SP; line
  pricing reports `no_system_sell_price: true` for it. (pytest)

## Templates (S3)
- AC-8. PUT product templates with `default_template_id` stores exactly one default; a default not
  among the ids is 422; GET returns `is_default`. A product with one link reports it as default.
  (pytest)
- AC-9. A line on a product with 2 published links and a default, sent with no pick, is stored with
  the default and Submit passes; with 2 links and NO default, Submit still refuses (unchanged).
  (pytest)
- AC-10. Combo links: PUT/GET `/dealer-kit/combos/{id}/tag-templates` (manage / view gates); a combo
  whose host is in another company is 404. (pytest)
- AC-11. A combo line whose combo has links uses the combo's (default) template in preview and on
  save; a combo with no links falls back to the host product's. Portal lookup with `?combo_id=`
  answers the combo's links. (pytest)

## Request combo (S4)
- AC-12. Parts on a host with no stored combo: refused `PARTS_NEED_COMBO` when `request_combo` is
  false (unchanged), accepted when true; parts in another company still refused. (pytest)
- AC-13. The resolved tag data of a request-combo line carries `combo_name` "HOST + PART + PART"
  and the summed parts' LP (C1: 1150 + 610 + 395 = 2155). (pytest)

## Extraction (S5)
- AC-14. `_extract_products` maps a model answer with `price_type`, typed prices and `set_codes`
  into lines: price type coerced (`"SP"`, `"selling"` -> selling; junk -> None), typed prices
  numeric or None (negative/huge/non-numeric -> None), set codes resolved through the resolver,
  `set_codes` capped at 10. (pytest, model stubbed)
- AC-15. A set line whose resolved parts equal a stored combo's fixed parts exactly returns that
  `combo_id`; one extra or missing part returns None. (pytest)
- AC-16. Prompt text for the price tag form no longer forbids prices and carries the LP/SP section
  rule; still forbids quantities; other forms unchanged. (pytest)
- AC-17. Gold set: 8 fixture messages (owner's paste split in 4, plus 4 re-typed real requests;
  outlet names fake) with the expected model JSON and the expected parsed lines, run through
  `_extract_products` with a stubbed provider. A separate opt-in live run (`RUN_LIVE_LLM=1`, dev
  Gemini key, cap USD 0.25) checks the real model against the same expectations. (pytest)

## Frontend (S6)
- AC-18. Slot `price` resolves to the SP figure on an SP line and the LP figure on an LP line;
  `price_label` resolves to "SP"/"LP". (vitest)
- AC-19. Line row: LP/SP toggle per line; new lines take the header default; the manual SP input
  is disabled on an LP line and on a line with a promotion. (vitest)
- AC-20. Eye icon per line opens that line's tag in a lightbox; disabled with no template.
  (vitest)
- AC-21. Template select preselects the default template. (vitest)
- AC-22. AI extract apply: price types, typed SP as manual SP (only with no promotion), set lines
  as combo (stored combo id) or request combo with parts. (vitest)
- AC-23. The "Add an item to see its tag before approving." text is gone. (vitest)
- AC-24. Product templates section and combo modal: choose the default; combo modal shows the
  templates field. (vitest)
