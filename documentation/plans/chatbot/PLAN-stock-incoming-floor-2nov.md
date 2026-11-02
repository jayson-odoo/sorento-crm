# PLAN: the stock check and the ETA ask tell one shipment the same date (STOCK-INCOMING-FLOOR)

Status: built, reviewer READY + security PASS at 0d9be4c1ab; console pass and owner hand test next.
Size M since the owner's 2 Nov ruling (new wording, one shared rule). No migration, no new permission, no
screen change (no mock). The dealer stock check now applies the existing incoming field gate
(`estimated_arrival_date`), so a security review ran. Fix A (02f3c71c78) was superseded by Fix B.
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

## Fix A (first round; superseded by Fix B)

The first round floored today on the TOLD date (promised + the contact's buffer) instead of the bare
promised date, through `told_offsets` and an `offsets` parameter on `earliest_packing_list_shipment`.
It was reviewed READY at 02f3c71c78. Fix B replaced it: once a past told date stays incoming (marked
"(delayed)"), a today floor has nothing left to decide, so its code is gone.

## Fix B (owner ruling 2 Nov 2026, card answers relayed by crew)

Owner: "the idea is to have the same presentation when ask eta and ask stock, meaning in incoming we answer
ETA xx, in stock ask also answer the same, unified behaviour". Crew decided the card from that rule and the
13 Oct ruling: Q1 (a), Q2 (a), Q3 (a), Q4 as written, Q5 (a). The owner can flip any of them in his hand test.

ONE shared read gives a dealer's told dates for a product code. Both paths print exactly those dates:

- Stock check, no stock: `CODE x 2: ❌ No stock, ETA 03/11/2026, 06/11/2026.`
- ETA ask: `CODE: ✅ ETA 03/11/2026, 06/11/2026`

The rules of the shared read:

1. Q1 (a): the set is the ETA ask's: every still-incoming line (`_still_incoming_filter`) on a non-draft
   shipment, within the contact's packing list regions and the company scope, with a non-NULL ETA.
   A packing list is NOT required. The packing list only decides which file goes with a stock check
   answer (the earliest still-incoming shipment that has one, and only when the contact's toggle is on).
2. Q2 (a): the promised date is the revised date when one is set (`coalesce(eta_delay_date,
   estimated_arrival_date)`, 13 Oct ruling), told as the ETA itself and never labelled as a delay.
3. Told date = promised + the by-code offset when the contact's ETA buffer switch is on
   (`_offsets_by_product_code`, the larger offset for a code two companies carry).
4. Q3 (a): every distinct told date, sorted. Q4: a told date before today (MYT) is followed by the ONE
   constant marker `(delayed)` (ms `(lewat)`, zh `（延迟）`). It is never "no incoming", and a past date is
   never shown without the marker (R10).
5. Q5 (a): a code with no dated still-incoming shipment has no dates. The stock check says
   "No stock and no incoming" and the ETA ask says "No ETA" (unchanged).

Unchanged: a windowed ETA ask ("arriving next week"), `/shipments` (no product), staff and non-dealer
contacts, the in-stock and too-big branches, and all wording other than the date list.

The ETA field revoke (security review; crew ruling (a)): a dealer whose gated
`estimated_arrival_date` is revoked gets no dates on either path. The ETA ask keeps "No ETA" (the
shared read is skipped when the field is denied), and the stock check now honours the same revoke and
says "No stock, No ETA." for a shipment still coming. That closes a gap that predates this PR: the
stock check never called the field gate. AC-SIF13, AC-SIF14.

Fix A's today floor (`earliest_packing_list_shipment(not_before, offsets)`, `told_offsets`) has no job
left once a past told date stays incoming, so it is removed rather than kept as a dead path.

### ARCHITECTURE

- Layer: service. `eta_policy` owns "what dates is this contact told": `told_dates` (the one read),
  `told_text` (the one formatter), `DELAYED_MARK` (the one marker). `incoming_stock_service` keeps the
  shipment predicates and `earliest_packing_list_shipment`, which now only picks the packing list file.
  `StockService` (stock check) and `_for_contact` (ETA ask, `/list` and `/by-product`) both call the read.
- Field gate: both paths honour a revoke of `estimated_arrival_date` (`field_access.decide` on the stock
  check, the route's `field_access.denied` on the ETA ask).
- Localizer: the marker and "No stock, No ETA." are rewritten in `Localizer.tail` / `reply` for ms and zh.
- Classes fixed: every dealer product whose stock check and ETA ask told different things (the floor
  before the buffer, a packing list required on one path only, the revised date read on one path only,
  earliest-only vs every date, and a field revoke honoured on one path only).

## Tests (red first)

- Fix A: red 38b805dda6, fix 106fbeabb4 (superseded).
- Fix B: red 7c6da3eec1 (AC-SIF1..12 in `tests/test_incoming_contact_rules.py` via `_ask_both` /
  `_assert_told`, which compare the stock check with `/list` and `/by-product`; translation in
  `tests/chatbot/test_chat_language_delayed_mark.py`), fix 5fcbbf3995.
- ETA revoke: red 3ab56b4ded (AC-SIF13/14, MCP `test_presenters_availability_lines.py`), fix 2d52e4e923.
- Fixed-date dealer tests pin `incoming.today_myt` so the "(delayed)" marker is deterministic.
- Reviewer guards: the merged-code file pick, and a draft shipment and a received line that are not told.

Guards run: `tests/chatbot/test_import_boundary.py`, `tests/chatbot/test_customer_asks_refer_only.py`,
the wide set of importers, and the MCP suite. No parser or prompt text is touched, so no eval gate.
