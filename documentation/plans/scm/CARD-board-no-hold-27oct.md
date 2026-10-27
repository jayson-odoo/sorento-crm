# Behaviour card: a Fulfilment Planning decision is a plan, not a stock hold (BOARD-NO-HOLD, 27 Oct 2026)

Owner, 27 Oct ~17:55 MYT: "board decision don't hold stock, board decision is just a planning choice".

**Owner answers (27 Oct ~18:05):** Q1 (a). Q2: "should be same as now" - no new mechanism: a
decided line that ends short stays decided as today (out of the board queue) and its short shows
in Stock Debt like any other short line; no "Plan not covered" re-entry, no automatic buy demand.
Owner answers (27 Oct ~18:15): Q3 "borrow should work like today": Borrow is out of scope and
unchanged in every way (it keeps holding, Stock Debt pin and "lent to" as today); only Reserve
stops holding. Q4 yes (a): reorder runs stop deducting Reserve from retail planning supply; the
same Reserve also lowers a project line's own Buy (Lane F), kept as today (owner 27 Oct ~22:25:
"can keep as today"). Q5: no wording change except a Reserve no longer reads "pinned" / held.

Plan: `documentation/plans/scm/PLAN-board-no-hold-27oct.md` (code map with file:line).
Dry run: `sorento_crm_backend/scripts/board_no_hold_dry_run.py` (read only, rolled back).

## The rule, in plain words

A confirmed Reserve or Borrow on the Fulfilment Planning board says WHERE a line is planned to be
supplied from. It no longer takes that stock away from anybody. Stock Debt, the board's
free / held strip, location stock and the ladder all read the stock as free; who actually gets a
pile is decided by date, earliest need first, the same walk every undecided line already takes.

What still binds first, unchanged: AutoCount's own reserved quantity (already off on hand), a
placement on an SPO or PO through an Order Inquiry, goods that landed for a line's own purchase,
and a PO / SPO whose S/O names the sales order. None of those is a board decision.

## What changes, by screen

| Where | Today | After |
| --- | --- | --- |
| Stock Debt walk | A decided line takes its stock first, at any date (status `pinned`) | A decided line draws its planned location at ITS OWN date, in date order with everyone who may draw there |
| Board free / held strip, location stock | Free = on hand - AutoCount reserved - decisions | Free = on hand - AutoCount reserved; "held" shows 0 for decisions |
| Ladder (what the board proposes) | Another order's decision is not offered | Stock planned for a later order is offered to an earlier need |
| Confirm on the board | A Reserve is capped at on hand less other orders' decisions there (the rest recorded short) | Capped at on hand only; two plans may name the same stock |
| Reorder runs | Reserve / Borrow qty is taken off retail planning supply | Not taken off (question 4) |
| OI reserve (CS reserves in AutoCount) | Lowers the OI ORDER row's buy demand | Unchanged |

## Real examples

1. **CB4702** (the owner's case). SO400884, required 28 Dec, confirmed "Reserve from BRW 36" on
   21 Aug. SO426986 needs the product earlier and reads short today because the 36 are taken
   first. After: SO426986 queues ahead of SO400884 for whatever it may draw. If SO426986 has no
   plan on BRW yet, the board now offers it "Reserve from BRW" (the 36 read free); once planned,
   it is served first and SO400884 reads short, with its plan shown as not covered.
2. On the dev copy (crew investigation): 184 decision holds, 16,647 qty, over 38 SOs and 94
   products. None of them is reserved in AutoCount (`quantity_reserved` = 0 on every row; 0
   transfers moved), so today the stock is held in the CRM only.
3. 53 of those holds (3,027 qty) are due more than 30 days after an earlier short line of the
   same product: these are the lines that change hands.
4. Examples 4 and 5, with the per-product totals, come from the dry run on the crew copy
   (requested in a `crew-data-request:` comment) and are added under this card.

## Edge cases

- **Cross-group plans.** Today the only way stock moves between ownership groups in Stock Debt is
  a confirmed decision (`supply_assignment.py:36-43`). Dropping the hold alone would make every
  cross-group plan read short in its own group. So the plan keeps one job: the line may draw the
  location its plan names (in date order), on top of its own group's pile.
- **Site pool (BRW) plans.** An undecided project line never draws a site pool in Stock Debt;
  dealer lines do. After the change a dealer line due before a planned project line can take
  pool stock first. That is "first need first" applied to the pool too.
- **Old decisions with no decision record** (confirmed before Stage 1C): treated the same, they are
  board decisions too.
- **Delivered lines**: unchanged, AutoCount delivery already lowers on hand.
- **Borrow** (8 rows / 207 qty on the copy): question 3.

## Questions (at most 5)

1. **What a confirmed decision still does.**
   (a) It stays the plan: shown on the board and in the Stock Debt drill, lets the line draw the
   location it names (in date order), and still drives the transfer proposals, OI rows and emails
   it drives today. It no longer holds stock anywhere.
   (b) As (a), but its location is only a label: the line draws its own group's pile only.
   **Recommendation: (a)**, because (b) makes every cross-group plan read short on the day it is
   confirmed.
2. **A decided line that ends up short.**
   (a) It returns to the board queue, marked "Plan not covered", with the old plan shown and the
   earlier order that took the stock named; CS re-plans it (a Buy there raises the OI ORDER row as
   today).
   (b) Its Stock Debt shortfall becomes buy demand automatically, without CS.
   **Recommendation: (a)**, because purchasing's only project demand today is OI ORDER rows
   (`demand.py:55-75`); an undecided project line is not buy demand either, so (b) is a second,
   new demand route that bypasses CS.
3. **Borrow decisions and "lent to".**
   (a) Same as Reserve: a plan only; the donor's "71 lent to SO415472" stays as an information note
   ("planned for SO415472: 71"), and the borrow's buy-back OI row stays as today.
   (b) Retire Borrow as a decision kind (with no holds there is nothing to borrow from).
   **Recommendation: (a)**, because 8 live rows still name a buy-back and retiring the kind is a
   separate change.
4. **Reorder runs.**
   (a) Stop taking Reserve / Borrow qty off retail planning supply, like every other screen.
   (b) Keep that one deduction, so a retail run does not buy against stock a project plans to use.
   **Recommendation: (a)**, because one rule everywhere is the ruling; project needs reach
   purchasing through OI ORDER rows, and a project line that loses the stock comes back via
   question 2.
5. **Wording.**
   (a) Board: "Planned: Reserve BRW 36"; when not covered: "Plan not covered, short 36 (SO426986 is
   due first)". Stock Debt drill: "Plan: BRW" beside the line; a decided line no longer reads `pinned` (placements still do).
   (b) "Decision: Reserve BRW 36" / "Decision short 36".
   **Recommendation: (a)**, because it says what it is, a plan, with no internal words.
