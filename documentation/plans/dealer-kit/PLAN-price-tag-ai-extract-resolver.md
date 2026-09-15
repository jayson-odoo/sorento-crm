# PLAN: price tag AI extract matches through the entity resolver; Add part only on a product with a combo

Status: BUILDING 15 Sep 2026 (owner go, chat 15 Sep)
Domain: dealer-kit
UAC: price-tag-ai-extract-resolver-acceptance-criteria.md
Branch: fix/price-tag-ai-extract-resolver  (lane stack :3080 / :8080)

## Why

Owner screenshot 15 Sep: an AI Extract of a 13-line sales order on the portal price tag form
reads "Not found" on 11 rows. Nine of those codes exist as active products. The extract path
has its own matcher, twice, and neither normalises separators:

- BE `app/services/ai_extract/extract_service.py` `_canonical_product_code`: `product_code ILIKE raw`
  with no `%` and no dash/whitespace stripping. `Srt6536 DIY` never meets `SRT6536-DIY`.
- FE `PriceTagRequestForm.tsx` `handleAIExtracted`: one `lookupTagItems(code)` call per row, then
  `i.code.trim().toLowerCase() === code` exact equality. Same failure.

`/api/v1/system/references/resolve` already answers this correctly through
`app/services/entity_resolver.py` (`_probe_product`, `_probe_product_set`): both sides
whitespace-and-dash stripped, casefolded, exact match, company-scoped, sets included.

Owner's rule (15 Sep): **one matcher.** Every entity match in the product goes through
`resolve_references`, so a change to the resolver reaches every consumer. The price tag AI
extract is the consumer fixed here; the FE keeps no matcher of its own.

Second finding, same screenshot: every product line shows an "Add part" search, including a
product that has no combo. Owner: if the product has no combo, there is nothing to add a part
to. The combos lookup already answers "this product has no combo"; the form ignores it. Also
enforce it on save, so the portal cannot post parts onto a no-combo product.

Third finding (owner screenshot 15 Sep, request PT-202609-0004 detail page, Lines tab): a
product with no combo still renders as two rows, the line row with empty price columns and a
"1a" tag row carrying the price, tag status and Design action. Owner: with no combo, just one
row per product; no 1a / 2a.

## Decisions

- D1 `_canonical_product_code` is deleted. `_extract_products` calls `resolve_references(db,
  codes, allowed_entity_types={"product", "product_set"}, enable_prefix_fallback=False,
  enable_embedding_fallback=False, max_candidates=len(codes))` ONCE for the whole list, inside
  the portal token's `company_scope` (the same scope the sibling lookups in
  `portal_price_tag.py` use). Exact tier only, because a prefix or semantic guess prints a tag
  for a product the sheet did not name. Both flags are parameters, not code, so widening later
  is a one-line change.
- D2 `ExtractedProductLine` gains `match: Literal["product", "product_set"] | None`,
  `product_id: str | None`, `product_set_id: str | None`. Exactly one match: `product_code` and
  `product_name` become the canonical row values, `match` and the id are set. No match, or an
  ambiguous token (more than one scoped hit): `match` is `None`, the ids are `None`, and
  `product_code` keeps the raw extracted text so the dialog can show what was read.
- D3 The FE drops the per-code `lookupTagItems` call and the equality check. `handleAIExtracted`
  reads `match` / `product_id` / `product_set_id` off the payload and builds the same
  `{kind, id, code, name}` record `aiMatchesRef` already holds, so Apply is untouched. Status
  `'loading'` disappears: the answer arrives with the extract.
- D4 `showParts` in `LineRow` becomes `!isSet && !!line.product_id && line.combos_loaded &&
  line.combos.length > 0`. Existing part rows (a reopened draft) still render with their
  Remove; only the "Add part" search is hidden. Supersedes AC-S2-4 of the combos plan ("on any
  line, combo or not").
- D5 Server: `PriceTagRequestService._add_line_parts` (and so `replace_lines` and create) raises
  the existing validation error shape (422, naming the line index) when `parts` is non-empty and
  the line's product has zero `ProductCombo` rows. A `product_set` line is already skipped.
- D7 Detail page Lines tab (`PriceTagRequestDetail.tsx`, the `request.lines.map` table): a
  line with exactly ONE tag and NO parts renders as a single row. That row is the line row with
  the tag's cells folded in: List Price, Sell Price (+ override), Tag status
  (Designed / No tag / Changed) and the Actions cell (Review / Design) come from the one tag;
  the `1a` label is not shown; `aria-label`s keep the tag label so the existing tests' selectors
  still resolve. A line with parts, or two or more tags, keeps today's shape (line row, part
  rows, `1a` / `1b` tag rows). The line-level "Changed" roll-up is redundant on a folded row, so
  it is not shown there (the tag's own Changed pill is on the same row).
- D6 No new endpoint, no registry, no flag. One resolver call, one boolean in the FE, one guard
  in the service.

## Files

BE
- `app/services/ai_extract/extract_service.py`: D1, D2.
- `app/api/v1/public/ai_extract.py`: scope the extract in `company_scope` for the token's
  company if `extract()` is not already scoped there (check first; sibling
  `portal_lookup_product_combos` shows the pattern).
- `app/services/price_tag_request_service.py`: D5.
- tests: `tests/test_ai_extract_resolver_match.py`, `tests/test_price_tag_parts_need_combo.py`.

FE
- `app/(auth)/portal/lib/portal-client.ts`: `AIExtractedProductLine` gains the three fields.
- `app/(auth)/portal/components/PriceTagRequestForm.tsx`: D3, D4.
- `app/(protected)/dealer-kit/price-tag-requests/components/PriceTagRequestDetail.tsx`: D7.
- tests: `PriceTagRequestDetail.test.tsx` (one tag + no parts = one row; two tags = sub-rows),
  `PriceTagRequestForm.aiExtractApply.test.tsx` (update the mocks: no `lookupTagItems`
  call, statuses from payload), `PriceTagRequestForm.parts.test.tsx` (Add part hidden when
  combos empty, shown when one or more).

## Out of scope

Other AI extract consumers (`SubmissionForm` product codes for stock inquiry / purchase
request) keep receiving `product_code`; they gain the canonical code for free through D2 and
are not otherwise touched.
