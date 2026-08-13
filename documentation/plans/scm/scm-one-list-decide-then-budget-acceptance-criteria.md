# S11 - One list, decide first, check the budget after

Status: UAC written, not implemented

## Why

> "actually imo it should be just a list of products, whether it is covered by stock, within
> budget, over budget, no price yet, needs a level, stock allocations, ALL should be in 1
> table, 1 list, 1 data grid table, you don't tell me what's over or within budget, because I
> haven't decided which one i want to buy, which one i want to use existing stock, so that's
> the logic change, I need to decide first, before you tell me within budget or out of budget,
> with that said, during planning, I don't even need to specify the budget, I should check my
> budget at the end of decisions made for all products, then I check whether it is within my
> budget, if not, what can be done"

The screen currently sorts the work FOR the buyer, into six places, using a budget they have
not agreed to:

| today | rows |
| --- | --- |
| Within budget | 65 |
| Over budget | 771 |
| No price yet | 165 |
| Covered by stock | 98 |
| Needs a level | 0 |
| Stock allocation | ~1,700 |

Every one of those is the same question - what do we do about this product at this location -
answered in a different box. And the first split, the budget one, is made before the buyer has
decided anything, which puts the constraint ahead of the decision. A line lands in "Over
budget" because of a number the buyer never entered, and its position implies a verdict on
work they have not done yet.

The business does it the other way round: go down the list, decide each line, then add it up
and see whether the money works. If it does not, cut. That is the order this screen has to
follow.

## Journey

**Actor:** the buyer, weekly, with the plan open.

1. **One list.** Every planning line, one grid, one set of filters. Nothing is pre-sorted into
   a verdict. What the plan FOUND is a column (`Buy` / `Covered by stock` / `Needs a level` /
   `No price` / `Allocation`), not a place the row lives.
2. **Decide, line by line.** Each row offers the same decision: **buy this much**, **use the
   stock we already have**, or **skip**. The suggested quantity is filled in; the offsets that
   produced it (on hand, incoming SPO, outstanding PO) are **columns on the row**, not hidden
   in a popover, so declining one is a click in the table.
3. **Add it up.** When decisions are made, the buyer opens the budget review: what has been
   decided, what it costs, what is still unpriced.
4. **Then, and only then, the money.** The buyer enters the budget HERE. If the decided total
   fits, they confirm. If it does not, the screen says by how much and proposes what to cut,
   ranked, which they accept or overrule.
5. **Confirm.** The surviving decisions become draft purchase orders, as today.

## What changes, concretely

* The budget input **leaves the planning view**. It moves to step 4.
* `Within budget` / `Over budget` **stop being sections**. They become the OUTPUT of step 4,
  computed over decided lines only.
* `Covered by stock`, `Needs a level`, `No price yet`, `Stock allocation` **stop being
  sections**. They become values of one `Status` column, filterable.
* Drag-to-fund **is removed**. It existed only to move a row between two budget bands that no
  longer exist during planning. Losing it is what lets this become a real shared `DataGrid`
  instead of the hand-rolled grid (ARCHITECTURE-RULES compliance, gained rather than waived).
* The offsets from S10g **move out of the popover onto the row**.

## Acceptance criteria

### S11a - one list

* **AC-S11a.1 [FE]** GIVEN a run, WHEN the plan renders, THEN every planning line appears in
  ONE `DataGrid` with `tableLayout: { width: 'fixed', columnsResizable: true }`, whatever the
  plan found for it.
* **AC-S11a.2 [FE]** GIVEN the grid, WHEN it renders, THEN `Status` is a column with the
  values `Buy`, `Covered by stock`, `Needs a level`, `No price`, `Allocation`, and can be
  filtered to one or several.
* **AC-S11a.3 [FE]** GIVEN the grid, WHEN it renders, THEN NOTHING on screen says within or
  over budget, and no budget input is present.
* **AC-S11a.4 [FE]** GIVEN a run of ~4,200 lines, WHEN the grid renders, THEN every line is
  reachable by paging, sorting and filtering, with no silent cap.
* **AC-S11a.5 [FE]** GIVEN a row, WHEN it renders, THEN on hand, incoming SPO and outstanding
  PO are columns on that row, and the suggested buy quantity is editable in place.

### S11b - decide

* **AC-S11b.1 [FE]** GIVEN any row, WHEN the buyer decides, THEN the same three choices are
  offered: buy a quantity, use existing stock, or skip.
* **AC-S11b.2 [FE]** GIVEN a decision to use existing stock, WHEN it is taken, THEN the line
  contributes nothing to the buy total and is not turned into a purchase-order line.
* **AC-S11b.3 [FE]** GIVEN an undecided line, WHEN totals are computed, THEN it counts as
  undecided, NOT as a buy and not as a skip. Silence is not consent.
* **AC-S11b.4 [BE]** GIVEN a decision, WHEN it is taken, THEN it persists on the run, so
  paging away and back does not lose it.

### S11c - then the budget

* **AC-S11c.1 [FE]** GIVEN decisions have been made, WHEN the buyer opens the budget review,
  THEN it states how many lines are decided, how many are still undecided, the total cost of
  the buy decisions, and how many decided lines have no price.
* **AC-S11c.2 [FE]** GIVEN the review, WHEN a budget is entered, THEN it reports within or
  over, and by how much.
* **AC-S11c.3 [FE]** GIVEN the decided total is over budget, WHEN the review renders, THEN it
  proposes which lines to cut, ranked worst-value first, and each proposal is accepted or
  overruled individually. The existing greedy allocator is reused here, applied to DECIDED
  lines rather than to every candidate.
* **AC-S11c.4 [FE]** GIVEN decided lines with no price, WHEN the total is shown, THEN they are
  reported separately and never counted as zero.

## Decisions taken

1. **Undecided is a state, not a default.** The old screen treated a within-budget row as
   implicitly fundable. Here a line the buyer never looked at is `undecided` and is excluded
   from the total, with the count shown, so "I have not finished" cannot be misread as "there
   is nothing left to buy".
2. **The allocator survives, repositioned.** It is not deleted: it moves from deciding the
   plan up-front to proposing cuts at the end. Same ranking, applied later, as advice.
3. **No new endpoint. This is a frontend change.** Checked before planning for one: all four
   sources already return the same `ReorderRecommendation` shape, differing only in
   `rec_type` (`buy` 1,001 / `disposition` 3,130 / `covered` 98 / `needs_level` 0 on the live
   run), and every one of them already pages past the endpoint's 1,000-row cap and holds the
   whole set client-side. So the six bands are already one dataset that was being split four
   ways on arrival, and unifying them removes code rather than adding an endpoint. Server-side
   paging stays available if 4,229 rows in one grid turns out to be slow, but it is not a
   prerequisite and would have been speculative work.
4. **Stock allocation lines join the list read-only for now.** They are a disposition, not a
   purchase, so they carry the `Allocation` status and the use-stock decision, but they never
   produce a purchase-order line. Transfers remain parked.

## Open, deliberately

**What "use existing stock" does downstream.** It records the decision and keeps the line out
of the PO. It does NOT create a transfer or an allocation instruction, because transfers are
parked with CS. If that is wrong, it is a bigger change than this one.
