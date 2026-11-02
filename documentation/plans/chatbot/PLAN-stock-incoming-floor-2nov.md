# PLAN: the stock check and the ETA ask tell one shipment the same date (STOCK-INCOMING-FLOOR)

Status: in progress, small fix track (size S: under 300 changed lines, no migration, no auth/RBAC
change, no new ingest surface). Fix A building; Fix B waits for the owner.
UAC: `stock-incoming-floor-2nov-acceptance-criteria.md`.

## Problem (production WhatsApp, 2 Nov 2026)

A dealer asks a code with a quantity; the bot says "No stock and no incoming. Please refer to your
salesman." The dealer then asks for its ETA and the bot answers with two future dates.

Measured at 5ac2eb7fa6:

- Stock check with a quantity: `StockService.list_stock` availability mode reads the earliest packing
  list shipment through `StockService._shipments_from_today` (`inventory_service.py:657-664`), which
  passes `not_before=today_myt()` to `incoming_stock_service.earliest_packing_list_shipment`
  (`incoming_stock_service.py:186-254`, floor at `:234`). The floor compares the REAL promised date
  (`coalesce(eta_delay_date, estimated_arrival_date)`); the contact's ETA padding is added only later,
  in `_judge` (`inventory_service.py:1812`, `visible_eta(eta_date, y, contact_rules)`).
- ETA ask: `IncomingStockService.incoming_for_product` (`incoming_stock_service.py:373-490`) has no
  date floor unless the ask names a window (`:448-451`); the route pads through
  `eta_policy.apply_to_incoming` (offset read `_offsets_by_product_code`) and tells a dealer
  `eta_policy.dealer_view`.
- So a shipment due 20/10 with a 14-day category padding is told 03/11. On 2 Nov the stock check drops
  it (20/10 < 02/11) while the ETA ask tells 03/11.

The floor came from #1601 (d01ca05cbe, CHAT-FIND round 3, 13 Oct), which floored on the real date
before the padding existed on that read's date. The 13 Oct crew ruling quoted at
`incoming_stock_service.py:200-202`: "a delayed shipment that is still coming is never 'no incoming'".

## Fix A (this PR, no ruling needed)

The today floor compares the date the dealer is TOLD: the promised date plus that contact's padding
(when their switch is on), not the bare promised date.

One shared read for the padding, so the two paths cannot disagree again:

1. `eta_policy.told_offsets(db, products, rules)` returns `{product_id: days}`: the by-code offset the
   incoming routes already pad with (`_offsets_by_product_code`, a code two companies carry takes the
   larger offset), and 0 for every product when the contact's switch is off.
2. `earliest_packing_list_shipment` takes those `offsets`: a shipment qualifies when
   `promised + offset >= not_before`. The floor runs in Python over the ordered candidates (no
   `DISTINCT ON`), so the earliest shipment whose told date is still ahead answers.
3. `StockService` computes the offsets once, passes them to the read, and `_judge` pads the printed
   ETA with the SAME offset (no separate `effective_limits` y for the date).

Side effect, intended: a code merged across two companies is padded by the larger of their offsets,
the rule the ETA ask already follows (before, the stock check used the first id's own offset).

### ARCHITECTURE

- Layer: service. `eta_policy` owns "what date is this contact told" (offset read + `visible_eta`);
  `incoming_stock_service` owns which shipments qualify; `StockService` composes them.
- Shared mechanism: `eta_policy.told_offsets` is the one offset read for both the stock check and the
  incoming routes (`apply_to_incoming` keeps calling `_offsets_by_product_code`, the same function).
- Classes fixed: every product with a non-zero offset whose promised date is within `offset` days
  before today (dev 28 Oct: 273 of 672 products with open incoming).

### Known divergence left as is (UNVERIFIED count, out of scope)

The stock check also requires a packing list and a non-NULL ETA (R5/R10, owner ruled); the ETA ask
does not. A shipment with no packing list still reads "no incoming" on the stock check while the ETA
ask tells its date. Not this bug; named so the next lane does not rediscover it.

## Fix B (waits for the owner)

A shipment still coming whose TOLD date has already passed (52 on dev 28 Oct, plus every contact with
padding off). Options sent: (a) "No stock, ETA 23/10/2026 (delayed)."; (b) "No stock, incoming is on
the way, arrival date not confirmed yet. Please refer to your salesman."; (c) keep "no incoming"
(rejected: breaks the 13 Oct ruling). Crew recommends (b), with the ETA path following the same rule.

Slot: the Python floor in `earliest_packing_list_shipment` is the one place that sees "still-incoming
candidates exist, none told today or later"; B adds that state there and a branch in
`stock_ask_branch` + `presenters`. No test in this PR pins the past-told outcome.

## Tests (red first)

`tests/test_incoming_contact_rules.py` (the agreement file), today pinned to 02/11/2026:

1. The production case: offset 14, shipments promised 20/10 and 23/10, dealer with padding on; the
   stock check says incoming ETA 03/11/2026 and the ETA ask tells 03/11/2026, 06/11/2026; first equal.
2. Boundary: promised today minus offset is told today and is incoming.
3. Earliest still ahead wins: promised 01/10 (told 15/10, past) and 20/10 (told 03/11) answers 03/11.
4. Padding off: promised 20/10 (past) and 10/11; answers 10/11, never the padded 03/11.
5. Merged code, offsets 3 and 14 on the two companies' products: the stock check pads by 14.

`tests/test_earliest_packing_list_shipment.py`: `offsets` widens the floor per product only.

Guards: `tests/chatbot/test_import_boundary.py`, `tests/chatbot/test_customer_asks_refer_only.py`,
plus the touched suites (`test_stock_availability_block.py`, `test_incoming_contact_rules.py`,
`test_earliest_packing_list_shipment.py`, `test_incoming_region_filter.py`).

No parser or prompt text is touched, so no eval gate.
