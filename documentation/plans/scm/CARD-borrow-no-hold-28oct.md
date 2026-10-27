# Behaviour card: a Borrow on the Fulfilment Planning board is a plan, not a stock hold (BORROW-NO-HOLD, 28 Oct 2026)

Owner, 28 Oct ~00:20 MYT: "borrow shouldn't affect the planning also". This reverses Q3 of the 27 Oct
BOARD-NO-HOLD card (`CARD-board-no-hold-27oct.md`, "Borrow should work like today"). #1919 (merged,
3783f8c08b) already made a Reserve a plan only; this lane does the same for a Borrow.

Code read on main 71a43b3ba1 (carries #1919). Data: dev copy `sorento_cagent_stack` (15 Oct), read only.

## The rule, in plain words

A confirmed Borrow on the board says WHERE a line is planned to be supplied from (another order's
stock, or stock at another location). It no longer takes that stock away from anybody. Exactly what a
Reserve does since #1919:

- Free stock everywhere (board free / held strip, location stock, the ladder, the confirm figure) reads
  the stock a Borrow names as free. With Reserve already out, no board decision holds stock at all any
  more: free = on hand less AutoCount reserved.
- In Stock Debt the borrowing line may draw the bin its Borrow names, at ITS OWN date, in date order with
  everyone else who may draw there (the #1919 "route", `supply_assignment.py` walk rule 7, `Hold.route`
  :351-353, drawn at the line's own step :1088-1104). Today a Borrow is a pin taken first at any date
  (`stock_debt_service.py:1814`, `supply_assignment.py:749-752`).
- Deciding and confirming on the board keep working as today: the same ladder rungs, the same confirm,
  the same transfer proposal and buy-back Order Inquiry row (both read the decision, not the hold, below).

Still binding first, unchanged: AutoCount reserved, OI placements on SPO/PO (question 2), goods landed for
a line's own purchase, PO/SPO S/O pins.

## Real examples (dev copy, 15 Oct)

Live Borrows: 13 allocation rows on 8 SOs, 11 products, 144 qty written, 109 still held (rest delivered).
All are `other_location`; no `other_project` row exists on the copy.

1. **SRTSH1040, SO402757 line 8** (needs 100 by 1 Nov 2026, none delivered). Three Borrow rows from
   BRW-BB: 42 + 42 from two SO383872 lines (due 1-2 Apr 2027) and 16 from an SO415810 line (due 1 Apr
   2027). BRW-BB on hand 787. Today: 100 pinned to SO402757 first. After: SO402757 draws BRW-BB on 1 Nov,
   still ahead of its April donors, so it reads covered unless lines due before 1 Nov that may draw BRW-BB
   take the 787 first. The donors' board cells keep "42 lent to SO402757" (question 3).
2. **B2155-NL-BLUE, SO424707 line 80** (6, due 6 Oct 2026, overdue): Borrow 6 at BRW-BB from an SO397450
   line due 21 Jul 2027. BRW-BB on hand 904. No visible change: the borrower is the earlier need.
3. **TPE-9201-300, SO421287 line 17** (3, due 16 Nov 2026): Borrow 3 at the site pool BRW from an SO391687
   line due 1 Jan 2027. BRW on hand 1,181. Site pool: dealer lines due before 16 Nov drawing BRW are now
   served first; with 1,181 on hand nothing moves.
4. **Delivered: SO419851** (4 Borrow lines, each fully delivered) and **SO424764 line 432** (CB2519SS-DIY,
   100 of 100 delivered, Borrow 5): already hold 0 today (`held_qty_expr` caps at what is still owed,
   `project_supply_service.py:257-272`). No change.
5. **CB4702** (brief, prod copy, not re-queried here): SO426986 planned Buy reads Short 364 while SO400884
   Reserve BRW reads Covered 36. A line reaches BRW / another group's stock only through a plan. That is
   question 1, and this lane does not change it.

## Edge cases

- **The lending group's lines.** Stock Debt's "Lent to SO396071 (32)" is NOT a Borrow: it is the
  STOCK-DEBT-LENDABLE rule for landed goods (`stock_debt_service.py:2434-2442`, `supply_assignment.py:1148-1210`),
  untouched. In Stock Debt a donor line shows nothing about a Borrow today: it just finds less in its pile.
  After: it is walked by date like everyone else, covered or short. The only "lent to" for a Borrow is the
  board's donor cell, "71 lent to SO415472" (AC-L6, `project_fulfilment_board_service.py:2033-2082`), read
  from the active decision's snapshot, not the hold (question 3).
- **The transfer a Borrow proposes** (`project_supply_service.py:8806` -> `stock_transfer_service.py:171`,
  `TRANSFER_PROPOSED` :397) reads only the decision snapshot: unchanged. As for a Reserve since #1919, the
  pile may go to an earlier line in Stock Debt while the transfer is still proposed.
- **The buy-back Order Inquiry row** (`ORDER_BACK`, `project_order_inquiry_service.py:5741`, demand at the
  donor's warehouse `demand.py:525-549`) is built from the confirm payload, not the hold: unchanged.
- **Delivered goods, #1667's delivered-first rule** (open PR, rebasing onto #1919): it makes delivered qty
  consume Reserve then Borrow before Buy, on write (`delivered_credits`) and on read (`held_qty_expr`).
  After this lane no decision is a hold, so its read half only sizes the Stock Debt route; its write half
  is untouched. This lane bases on main and merges main again once #1667 lands.
- **Per-allocation-row cap quirk.** `held_qty_expr` caps each row at the line's whole owed qty, so several
  rows can net more than the line owes (SO402757: 42 + 42 + 16; after a partial delivery of 60 they would
  read 40 + 40 + 16 = 96 against 40 owed). Stock Debt caps per line (`assign()` :750). Once a Borrow is no
  longer a hold, no free-stock figure reads the quirk; only the route size does, and that is capped per line.
- **Confirm figures.** The Borrow rungs' donor figure (`_donor_impact` :9114, `_check_borrow` :6805) reads
  free stock, which will no longer net other orders' Borrows: two separate confirms may plan the same
  stock, and Stock Debt decides by date (as for Reserve after #1919). One confirm still cannot give the
  same pile twice. The per-donor-LINE ledger is question 5.

## Questions (at most 5)

1. **Reach without a plan.** Should a project line reach BRW / another group's stock by due date WITHOUT a
   Reserve or Borrow plan? Today only a plan gives that reach (`supply_assignment.py:36-43`, `may_draw`).
   (a) No, not in this lane: reach stays plan-only, as after #1919.
   (b) Yes: the parked 14 Oct full decouple (`PLAN-stock-debt-decouple.md` on the #1667 branch, :103-104:
   622 of 18,508 lines change status, dated shortfall +2.4%).
   **Recommendation: (a)**, because (b) changes far more than Borrow and the owner parked it on 14 Oct; it
   can be its own lane.
2. **Order Inquiry links to a PO / SPO.** Should they keep holding incoming stock for their line?
   Dev copy: 5,577 SPO + 10 PO links are automatic copies of AutoCount; 10 SPO links (1,479 qty) and 39
   "Reserved @ BRW" links (1,700) were made by hand (`order_inquiry_links.auto`, all links, not only open).
   (a) Yes, as today: they are purchasing's record, not a board decision.
   (b) Hand-made links stop holding; automatic ones keep it.
   **Recommendation: (a)**, because the ruling is about board decisions, and a link is what tells
   purchasing which incoming goods are for which line.
   Addendum (28 Oct): one kind of Borrow is itself such a link. A step-3 "supply" Borrow (taking another
   order's INCOMING SPO / PO) writes no allocation; Confirm moves the donor's placement onto the borrower as
   an `ORDER_BACK` row with the link (`project_supply_service.py:8956-8963`, `_place_supply_borrows`
   :7696-7730), and Stock Debt pins it like any link. With (a) it keeps binding the incoming goods to the
   borrower first. Making it a plan too would mean not moving the placement at all, a change to what
   purchasing sees, so **recommendation: (a), supply Borrows unchanged in this lane**; this lane changes
   stock Borrows (`other_location` / `other_project` allocations) only.
3. **The donor's "71 lent to SO415472" on the board.**
   (a) Keep it as today: it is the plan CS agreed with the donor, and it explains why the donor may read short.
   (b) Drop it, because nothing is held.
   **Recommendation: (a)**, no frontend change.
4. **Reorder runs.** Retail's figure deducts Borrow only since #1919 (`reorder_run_service.py:1335`, :2767).
   (a) Stop deducting Borrow too, like Reserve; the project half's own Buy keeps both (as today, #1919 Q4).
   (b) Keep deducting Borrow from retail.
   **Recommendation: (a)**, one rule everywhere; the same choice the owner made for Reserve.
5. **One donor line lent twice.** A group Borrow names a donor LINE. Confirm refuses a second Borrow
   from the same donor line beyond its open qty less what other active Borrows already took
   (`_group_borrow_held_qty` :9132, used at :7290-7298).
   (a) Keep that refusal: confirming works as today.
   (b) Drop it: two orders may plan the same donor line, Stock Debt decides by date.
   **Recommendation: (a)**, because the owner's condition is that deciding and confirming keep working as
   today; it is a confirm check, not a stock hold.
