# Supply Chain - Sales order changes after planning

Read this when a sales order changes after CS has already planned it: a manual edit, a
re-uploaded sales order book, or an AutoCount push. It explains what raises a change, what the
board suggests doing about it, and what Confirm or Amend actually does, for both CS and
purchasing.

## Where

* **[Supply Chain → Project Demand → Fulfilment Planning](/project-sales/fulfilment-planning)**
  (also reachable as **Project Sales → Fulfilment Planning**). This is where a change is
  reviewed and decided.
* **[Project Sales Admin → Sales Orders](/scm/sales-orders)**. A **Changed** badge appears under
  the SO number for any order carrying an undecided change; clicking it opens the board already
  on that order and that batch.
* The Fulfilment Planning list itself shows the same **Changed** badge under the SO number.
* **[Supply Chain → Project Demand → Planning changes](/project-sales/planning-changes)**
  (also reachable as **Project Sales → Planning changes**; page titled **Planning changes**)
  lists every batch that has ever been raised: **Uploaded**,
  **Uploaded by**, **Source file**, **Source**, **Orders**, **Lines**, **Pending**, **Applied**,
  **State**.

## What raises a change, and what doesn't

Three things can move a line's quantity, date or product after CS has already planned it:

1. A manual edit on the sales order's detail page (click **Edit**, change a line, click
   **Save sales order**).
2. Re-uploading the sales order book (Excel).
3. An AutoCount push (the ESB sync).

All three build the exact same before-and-after comparison and raise the same kinds of change:
qty up, qty down, date advanced (earlier), date delayed (later), line cancelled, line added, and
product changed (one product swapped for another on the same line, shown as a single row -
"Product changed, was &lt;old product&gt;" - never a cancelled-plus-added pair).

**A line nobody has decided on yet raises nothing.** If the line isn't held inside an active
decision and has no Order Inquiry row against it, the order simply shows its new value with no
badge and nothing to review - there's nothing a change could invalidate.

## What you see on the board

Open the **Changed** badge (or find the order on Fulfilment Planning). Each changed line shows:

* A **Was** / **Now** table: **Qty**, **Date**, **Decision**, one column each side.
* Underneath, the suggestion: one line per action, in plain words composed by the system, for
  example "Buy 234 (was 134)", "Reduce Buy 100 to 0", "Keep PO-A 100 of 134", "Reallocate PO-A 34
  to SO420103 ORDER 50".
* "Late by N days" when the line is kept but will still land after the date now needed.
* "Short N" when nothing found can cover the whole quantity in time.
* A cancelled line reads **Cancelled** straight across the **Now** column (no quantity, no date -
  there's nothing left to deliver).
* A product-changed line prints "Product changed, was &lt;old product&gt;" above its own
  suggestion.

## Confirm or Amend, nothing else

Every suggestion arrives already filled in, ready to post exactly as shown. There's no separate
"accept" step.

* **Confirm** posts every line still marked to confirm, for as many changed lines as the button's
  own count shows.
* To do something different on one line, open it (it opens read-only) and click **Amend** to
  unlock it. Change what covers the line yourself, then save. Confirm won't overwrite a line
  that's been amended - it posts what was decided for that line instead.

## What Confirm does to Order Inquiries

Carrying out a suggestion writes to the **Order Inquiries** page:

* **A top-up** (qty up on a held Buy) keeps the same row, at the new quantity, with a note
  reading "Was 134".
* **A Reduce or Release** cancels or reduces the row in place - it reads **CANCEL BALANCE** or
  **RELEASE**, with a note saying why (for example "Line closed", "Was 134").
* **A Reallocate** to another order's waiting row lands on that row as a note, for example
  "Found: PO-A 34" - that row's own state moves to **Linked** or **Partly linked**. Its own CS is
  never asked to approve it; their Order Inquiries row and their own board simply read the new
  state the next time they open it.
* With nowhere else for it to go, a pool-location row is raised instead, and the reorder engine
  counts it as available stock.
* **A Borrow** raises an **ORDER BACK** row on the donor order's own line, for the quantity it
  lent out.

## Removing a line, or setting its quantity to 0

On the sales order's detail page, removing a line, or editing its quantity down to 0, is accepted
even when the line is already held in a decision or already has an Order Inquiry row raised
against it (this used to be refused). The line is never deleted: it reads **Cancelled** and
becomes read-only (no **Remove line** button, its fields can't be edited), and the change still
raises normally so its stock or purchase-order quantity gets released or reallocated.

## The one signal

A decision used to be able to pick up a second, quiet flag ("Needs CS review") on its own,
separate from any change batch. That's gone - the **Changed** badge and its batch are the only
signal now. Something that simply moved with nothing to decide raises no flag at all; something
that does need a decision always arrives as a proper change batch with its own suggestion.

## How you'll be notified

* **CS:** nothing beyond the **Changed** badge itself - there's no toast or email for a change
  being raised. Check the badge on Sales Orders or Fulfilment Planning, or the **Planning
  changes** list for the full history.
* **Purchasing:** one notification per order once its change is actually applied (Confirmed or
  Amended), not one per line and not while it's still sitting on the board. It goes to every
  purchasing role, titled "Order inquiry &lt;SO number&gt;", stating how many instructions and how
  many still need buying.

## The reserve window

Stock is only held against a line due within 60 days (the same reserve window purchasing already
plans around). A line moved past that window loses its hold: any reserve or placed purchase order
against it is released or reallocated, and the line is bought again nearer its own new date.
Keeping the old purchase order instead of reallocating it is possible, but only as an Amend - it's
never the suggestion.

## A freed SPO share

Freed purchase-order quantity is reallocated automatically (to the dealer pool, to another
order that's waiting, or to a stock pile). A freed SPO (shipping order) share cannot be, because
only an **ORDER BACK** row is allowed to carry an SPO allocation, and none is waiting for it. It
is simply released instead - the suggestion reads "Release SPO &lt;number&gt; &lt;qty&gt;,
unallocated for purchasing". It shows up unallocated when purchasing checks incoming stock, and
someone in purchasing links it to the order that needs it by hand.

## Worked examples

All on SO419772 / B2155-NL-BLUE, own location BRW-IB, pool BRW, unless another order is named.

| # | What changed | The suggestion | What Confirm does |
|---|---|---|---|
| S1 | Qty up 134 to 234, Buy 134 raised, not on a PO, due 4 Sep (not immediate) | "Buy 234 (was 134)" - the top-up joins the same row. If a later order (SO419900, due 30 Nov) holds 234 on hand instead: "Borrow 234 from SO419900, order-back raised" and the Buy row is cancelled. | The row stays ORDER 234, note "Was 134". Borrow case: ORDER 134 cancelled (RELEASE note); ORDER BACK 234 raised on SO419900's own line. |
| S2 | Qty down 234 to 100, Buy 134 placed on PO-A, Buy 100 raised | "Reduce Buy 100 to 0", "Keep PO-A 100 of 134", "Reallocate PO-A 34 to SO420103 ORDER 50" (dealer pool instead if BLUE is dealer hot-selling). | Raised ORDER 100 cancelled (CANCEL BALANCE). Placed ORDER 134 becomes 100, note "Was 134", PO-A link trimmed. SO420103's row reads "Found: PO-A 34" (or a new pool-location row for 34). |
| S3 | Delayed 4 Sep to 20 Nov, Use own 134 reserved at BRW-IB (inside the reserve window), another order needs 80 sooner | "Reallocate 80 at BRW-IB to SO420100 ORDER 80" (its own Buy 80 becomes Use own 80); the rest re-sourced whole for 20 Nov, e.g. "SPO 134 on SPO-77 for 20 Nov" if it covers it in time, else Keep 134. | SO420100's ORDER 80 cancelled (stock covers it now). This line reads ALREADY INBOUND 134, covered by SPO-77, note "Was 4 Sep". Keep case: nothing changes. |
| S4 | Advanced 4 Sep to 20 Aug (still not immediate), Buy 134 placed on PO-A arriving 1 Sep | "Borrow 134 from SO419900, order-back raised" and "Reallocate PO-A 134 to SO419900 ORDER BACK 134" (PO-A lands well before SO419900's own date). | This line's ORDER 134 cancelled, note "Was 4 Sep". SO419900 gets an ORDER BACK 134 row linked to PO-A (Linked). |
| S5 | Line cancelled or removed, Reserve 50 plus Buy 84 placed on PO-B | "Release 50 to dealer pool" (or free at BRW-IB if not hot-selling) and "Reallocate PO-B 84 to dealer pool" (or to a waiting order, or a pool-location row). | ORDER 84 cancelled (RELEASE, note "Line closed"). PO-B's 84 links to whichever row received it, or a new pool-location row. |
| S6 | New line added on an order with held lines: B2160-NL-BLUE 60, due 4 Sep | One step for the whole 60: "Use own 60 at BRW-IB" if the group has it, else Borrow, else SPO, else Buy 60. | A new ORDER 60 row if bought; an ORDER BACK row if borrowed; no row at all if covered from stock. |
| S7 | Product changed: B2155-NL-BLUE 134 becomes B2155-NL-WHITE 134 | One row, "Product changed, was B2155-NL-BLUE": "Release 134 B2155-NL-BLUE, free at BRW-IB" (or reallocated as in S5), then "Buy 134 B2155-NL-WHITE for 4 Sep" (or whichever step covers it, as in S6). | The BLUE row is cancelled with a note that the product changed to WHITE, its PO quantity reallocated the same way S5's is. WHITE is raised fresh, per its own source. A BLUE PO is never relabelled WHITE. |
| S8 | Date and qty changed together: 134 on 4 Sep becomes 100 on 20 Nov, Reserve 134 | One run at (100, 20 Nov): "Reduce reserve 134 to 100" (the freed 34 reallocated as in S5), then answered the same way a delay is answered in S3. | One row, one outcome - there's no separate date-versus-qty tie-break. |
| S9 | Small delay, 4 Sep to 25 Sep, Reserve 134, nobody needs the stock sooner | "Keep 134." Nothing else. | Nothing changes on Order Inquiries. If it had been a Buy instead: still Keep, with the row's own note reading "Was 4 Sep"; a placed PO keeps its link. |
| S10 | Big delay, 4 Sep to 15 Mar next year, Reserve 134 (past the reserve window) | "Release 134, free at BRW-IB" (dealer pool if hot-selling) and "Buy 134 for 15 Mar." A placed Buy on a PO landing in October instead: reallocate that PO the same way, then buy again nearer 15 Mar (Keep is possible only as an Amend). | A new ORDER (or RESERVE & ORDER) row raised for 15 Mar; any cancelled or reallocated rows carry their own notes. |
| S11 | Advanced into the immediate window: 4 Sep to 3 days from now, Buy 134 raised, not on a PO | "Pool share 90 at BRW" now; the remaining 44 covered whole by one step (Use own if the group has it, else Borrow with an order-back), or shown as "Short 44" if nothing can cover it in time. | ORDER 134 becomes ORDER 44 ("Was 134"), or is cancelled if a borrow covered it; an ORDER BACK row if a borrow was used. The shortfall is shown plainly, never hidden. |
| S12 | Advanced but still not immediate: 4 Sep to 25 Aug, Buy 134 placed on PO-A arriving 28 Aug | If a donor can lend the whole 134: Borrow, order-back, and reallocate PO-A to the donor's order-back row (as S4). If nobody can: "Keep 134", flagged "Late by 3 days" - so CS can Amend to accept the lateness, or chase purchasing on the PO date outside the system. | Keep case: nothing changes on Order Inquiries; the lateness is recorded against the change itself, not the order-inquiry row. |

## What's captured

* One change batch per manual save, per book upload, or per AutoCount push - grouping every row
  that batch changed, who or what triggered it, and when.
* Per line: the before and after quantity/date/product, the composed suggestion, and whichever
  decision (Confirm or Amend) was made for it.

## What gets created

* Updates to the affected order's held decision and its Order Inquiry rows (top-ups, reductions,
  releases, reallocations, order-backs), as described above.
* A notification queued to purchasing once the order's change is actually applied.

## See also

* [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md)
* [Plan a sales order nobody decided](plan-undecided-lines.md) (a pending change puts a line
  carrying an order inquiry back in play)
* [Upload the data a reorder plan is built from](upload-plan-data.md) (the sales order book this
  flow reacts to)
* [Run a reorder plan](run-a-reorder-plan.md)
* [Order inquiry handover email to purchasing](order-inquiry-handover-email.md) - the parallel-run
  email this same Confirm/Amend triggers, separate from the in-app notification above
