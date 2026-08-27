# UAC - Order units, ladder v6

Engine (pytest, `tests/scm/test_ladder_v6_order_unit.py`, Postgres via `tests/_pg_fixture.py`, seed your own chain):

- AC-U1 Two lines of one SO, same item / location / required date, 10 and 20; own group net <= 0; the site pools net 0; another group holds 12 free. v5 gave Borrow 10 + Buy 20. Now: **Buy 10 and Buy 20**, both `rung == "buy"`, both reasons the whole-unit sentence naming 12 of 30 coverable.
- AC-U2 Same two lines, the pool nets 63 and BRW holds 63 free: line 31 Reserve 10 from BRW, line 32 Reserve 20 from BRW (one unit draw, split in line order), pool ledger drawn 30 once.
- AC-U3 Same two lines but required dates differ: two units, the v5 result stands (Borrow 10, Buy 20).
- AC-U4 Same two lines but fulfilment locations differ: two units.
- AC-U5 A component straddling two lines keeps kind, source_location, rung and reason on both halves; the members' quantities sum to the component's.
- AC-U6 `proposal_for` (sheet), `_compose_for_freeze` and the board give the same composition for the same order (pin one scenario across the three).
- AC-U7 Every existing ladder v4 / v5 test passes unchanged (single-line units are today's behaviour).
- AC-U8 `unit_qty` and `unit_line_count` present in the board contribution and the sheet line payloads (assert in a response test; `response_model` drops undeclared fields).
- AC-U9 One SO, four lines of one item at one location on four required dates (10, 12, 10, 5); own group net <= 0; the pools net 0; ONE other-group donor with 10 free. In walk order: line 1 Borrow 10 (whole), lines 2, 3 and 4 Buy whole - the donor is drawn down exactly once across the walk, not offered to every date. `_compose_for_freeze` gives the same answer as the board for that order, since it is the confirm path that refused it ("BRW-SYNT has 0 free, and 10 was asked for", 28 Aug).

Frontend (vitest):

- AC-F1 The source-info tooltip carries the unit sentence when `unit_line_count > 1` and nothing extra otherwise.
