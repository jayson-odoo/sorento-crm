# UAC - Order units, ladder v6

Engine (pytest, `tests/scm/test_ladder_v6_order_unit.py`, Postgres via `tests/_pg_fixture.py`, seed your own chain):

- AC-U1 Two lines of one SO, same item / location / required date, 10 and 20; own group net <= 0; the site pools net 0; another group holds 12 free. v5 gave Borrow 10 + Buy 20. Now: **Buy 10 and Buy 20**, both `rung == "buy"`, both reasons the whole-unit sentence naming 12 of 30 coverable.
- AC-U2 Same two lines, the pool nets 63 and BRW holds 63 free: line 31 Reserve 10 from BRW, line 32 Reserve 20 from BRW (one unit draw, split in line order), pool ledger drawn 30 once.
- AC-U3 Same two lines but required dates differ: two units, the v5 result stands (Borrow 10, Buy 20).
- AC-U4 Same two lines but fulfilment locations differ: two units.
- AC-U5 A component straddling two lines keeps kind, source_location, rung and reason on both halves; the members' quantities sum to the component's.
- AC-U6 `proposal_for` (sheet), `_proposals_for` (the freeze) and the board give the same composition for the same order (pin one scenario across the three).
- AC-U7 Every existing ladder v4 / v5 test passes unchanged (single-line units are today's behaviour).
- AC-U8 `unit_qty` and `unit_line_count` present in the board contribution and the sheet line payloads (assert in a response test; `response_model` drops undeclared fields).
- AC-U9 One SO, four lines of one item at one location on four required dates (10, 12, 10, 5); own group net <= 0; the pools net 0; ONE other-group donor with 10 free. In walk order: line 1 Borrow 10 (whole), lines 2, 3 and 4 Buy whole - the donor is drawn down exactly once across the walk, not offered to every date. `_proposals_for` gives the same answer as the board for that order, since it is the confirm path that refused it ("BRW-SYNT has 0 free, and 10 was asked for", 28 Aug).

Frontend (vitest):

- AC-F1 The source-info tooltip carries the unit sentence when `unit_line_count > 1` and nothing extra otherwise.

Added by the review rounds of 28 Aug, same file, same substrate:

- AC-U10 A unit's own proposal is CONFIRMABLE, end to end through the confirm route. Two shapes, because the recheck derived two different figures per line: (a) floor plus pool, AC-U5's fixture (own 5, pool 25, lines 10 and 20) - line 31 is proposed 5 from its own location off the UNIT's offer while its own line offer is 0; (b) floor plus water (group nets 0 with 10 on hand and an SPO of 20 in time, lines 10 and 20) - the split hands the whole 20 of water to line 32, whose own line-level water share is 10. Both must confirm as proposed, nothing amended.
- AC-U11 The board's proof reads the walk's donor ledger: on AC-U9's fixture, question 3 on the second delivery date does not say "free stock at ..., within the cross-group borrow limit", and the Buy's own sentence does not offer the donor the first date spent.
- AC-U12 A covered line is out of the unit on the sheet as it is on the board, AND its hold stays on the floor. Group -BB, sibling holding 25, group SPO 20 timely, line 31 (10) covered with a real allocation of 10 at the sibling, line 32 (20) open: all three surfaces say Reserve 15 at the sibling plus Timely SPO 5, and confirming line 32 as proposed succeeds. The covered line's OWN live proposal still un-nets its own hold, because "Compose again" starts the planner from it.
- AC-U13 One covered set for the recheck and for the freeze: a line named in `uncover_line_ids` is released by that same transaction, so it is in the walk and in the unit. Own 5, pool 25, line 31 (20) named and line 32 (10) covered-then-uncovered; confirming line 31 as Reserve 5 own + 15 pool succeeds and writes revision 2.
