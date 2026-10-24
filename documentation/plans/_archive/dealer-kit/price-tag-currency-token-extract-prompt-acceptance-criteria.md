# UAC: price tag currency token + AI extract prompt

Plan: `PLAN-price-tag-currency-token-extract-prompt.md`. Each AC is testable; the tester writes the red test
named beside it before the coder starts.

## A. Text prices and the currency token

- AC-A1 A text layer slot-bound to `sell_price` renders `535` for an offer of 535, not `RM 535`.
  (vitest product-block)
- AC-A2 A text layer slot-bound to `list_price` renders `1,599` for a list price of 1599: grouping kept, no
  cents, no prefix. (vitest product-block)
- AC-A3 `{{product.sell_price}}` and `{{product.list_price}}` merge fields render the same bare figure as
  AC-A1/A2. (vitest merge-fields)
- AC-A4 A price BADGE layer with `showCurrency` absent still renders `RM 760`; `formatTagPrice(760)` default is
  unchanged. (vitest price-badge)
- AC-A5 `{{product.currency}}` renders the bound product's currency (`MYR` for a product row whose payload
  carries `currency: "MYR"`; `SGD` when the payload says `SGD`). (vitest merge-fields)
- AC-A6 `{{product.currency}}` on a line-bound tag renders the line's currency; on a set renders the set's;
  on a layer with a part subject (`subjectPart: n`) renders that PART's currency, not the parent's (D7).
  (vitest merge-fields)
- AC-A7 A payload with no `currency` field (older pinned row) renders `MYR`, never an empty string or the raw
  token. (vitest merge-fields)
- AC-A8 The Insert field list contains `product.currency` labelled `Currency` in group `Product`, placed after
  Sell price. (vitest merge-fields)
- AC-A9 `hasSubjectAwareToken('{{product.currency}}')` is true, so the subject picker shows for a layer that
  reads it. (vitest merge-fields)
- AC-A10 Backend `product_tag_data` returns `currency` equal to the product's `currency` column; a product
  with `currency='SGD'` returns `SGD`. (pytest tag_data)
- AC-A11 Backend set data returns `currency` (first member's), and a line tag row + each part row returns
  `currency`. (pytest tag_data)
- AC-A12 The tag data route response JSON includes `currency` on the product row and on a line tag row and
  its parts (response_model declares it). (pytest tag_data_routes)
- AC-A13 Browser: on the lane stack, a text layer with content `{{product.currency}} {{product.sell_price}}`
  shows `MYR 535`-style text on the canvas; the badge on the same template still shows `RM`. Evidence PNG under
  `documentation/plans/dealer-kit/evidence/price-tag-currency-token/`.

## B. AI extract prompt, per form

- AC-B1 `extract_prompt_key("portal.price_tag_request") == "ai_extract_portal_price_tag_request"`; for every
  form key in the schema registry and in `_ENTITY_TO_FORM_KEY`, `PROMPT_KEYS[extract_prompt_key(k)]` exists with
  `active=True`, `variables=[]`, non-empty fallback. (pytest ai_extract_service)
- AC-B2 Only the price tag key's fallback contains rules (1) to (7) AND rule (8) with `REQUIRED` and
  `every product code`; `ai_extract_portal_purchase_request`'s fallback has no rule (8). (pytest)
- AC-B3 `_build_messages(form_key, ...)[0]["content"]` equals `get_prompt(db, extract_prompt_key(form_key)).text`;
  a production-label override on the price tag key changes the price tag system text and does NOT change a
  purchase request build. (pytest)
- AC-B4 The price tag user message line-items clause has no `Optionally` and references rule 8; other line-item
  forms have no `Optionally`; a form without line items still forbids the `products` array. (pytest)
- AC-B5 System Management > AI Assistant prompts list shows `ai_extract_portal_price_tag_request` with the rule 8
  default. (browser, evidence PNG)
- AC-B6 Live: the 21-line paste from 16 Sep extracts 21 product lines on 3 of 3 runs through
  `AIExtractService._run_extract`. (manual, captain runs, result recorded in plan)

## C. Live red dot, no Update all

- AC-C1 `useTagDataChanges` sets `refetchInterval` 30000, `refetchIntervalInBackground` false,
  `refetchOnWindowFocus` true, and is disabled when the request status is terminal (collected, rejected, void).
  (vitest hook)
- AC-C2 Designer: when the polled data changes from no changes to one tag changed, the rail shows the red dot on
  that tag without a remount or reload. (vitest RequestTagDesigner.rail)
- AC-C3 Detail header: the `Product data changed · N` pill follows the polled data the same way. (vitest detail)
- AC-C4 No `Update all` button renders in the detail header at any count; `updateAllTagPins` is gone from the FE
  service. (vitest detail; grep gate)
- AC-C5 Pin decisions (update / keep) and recheck refetch the hook; the dot clears after `update` on that tag.
  (vitest)
- AC-C6 Browser: edit a product's list price on the lane stack while its designer is open in another tab; within
  30 s, or on refocusing the tab, the red dot appears on the tag. Evidence PNG.

## D. List indicator from the stored count

- AC-D1 Migration `ptag_0012_data_change_cache` adds `data_changed_tag_count` (int, not null, default 0) and
  `data_checked_at` (timestamp, null) to `price_tag_requests`; single alembic head. (pytest migration)
- AC-D2 `store_data_change_count` writes the number of tags with changes and a timestamp; a terminal request stores
  0. (pytest)
- AC-D3 `touched_request_ids`: touched when `data_checked_at` is null, when the line's product `updated_at` is
  later, when a `product_specifications` row of that product updated later, when the line's promotion updated
  later, when a set member of the line's set updated later, when a product attachment was created later; NOT
  touched when `data_checked_at` is after all of them; never touched when terminal. (pytest)
- AC-D4 List route: a touched row returns a refreshed `data_changed_tag_count` and now has `data_checked_at`;
  an untouched row returns its stored count and the resolver is not called for it. (pytest routes, monkeypatch
  the resolver to count calls)
- AC-D5 `PriceTagRequestListItem` carries `data_changed_tag_count` in the JSON body. (pytest routes)
- AC-D6 `PriceTagRequestsList` renders a `Product data` column with the amber `Product data changed · 2` pill for
  count 2 and an empty cell for 0; column has an explicit `size`. (vitest)
- AC-D7 Browser: after AC-C6's product edit, the list page shows the pill on that request. Evidence PNG.

## Gates

- `npx vitest run lib/dealer-kit "app/(protected)/dealer-kit/price-tag-requests"` green.
- `pytest tests/test_dealer_kit_tag_data.py tests/test_dealer_kit_tag_data_routes.py tests/test_ai_extract_service.py tests/test_price_tag_data_pin.py <new list/migration tests> -q` green.
- Single alembic head after `ptag_0012`. Reviewer + security-reviewer once per lane.
