# Supply Chain - Plan a sales order nobody decided

Read this when an order was never planned, including one that already reads **Completed** and
shipped, and when you want to tell from the Sales Orders list which orders still need planning.

## Where

* **[Project Sales Admin → Sales Orders](/scm/sales-orders)** - tick the orders, then
  **Start** → **Plan selected (N)**.
* **[Supply Chain → Project Demand → Fulfilment Planning](/project-sales/fulfilment-planning)**
  (also reachable as **Project Sales → Fulfilment Planning**) - the board that opens.

## Which lines the board plans

The board asks who has decided where a line's stock comes from. It does not ask whether
delivery is still outstanding, so **a line that has already been delivered is still planned if
nobody decided it**. The stock left the bin with nothing behind it, and that unit has to be put
back.

A line counts as **decided** when either of these is true:

* a confirmed decision on the board covers it, or
* it carries a live order inquiry row (one raised outside the board, typically by the Order
  Inquiry sheet upload) that is neither cancelled nor rejected by purchasing. Purchasing has
  already been told to buy it.

A decided line is on the board read-only: no suggestion, no tick box, and it is not counted in
**Confirm (N)**. On the **List** view its **Suggested** cell reads **Not recorded** and its
**Decided** cell names the inquiry number instead of a composition.

Everything else is planned:

* a line whose only inquiry row was cancelled, or whose row purchasing rejected and nobody has
  answered yet;
* a line put back in play by a pending planning change. Once the book moves a line, the
  instruction purchasing holds is out of date, so the line is proposed for again (its **Changed**
  badge is the route in - see [Sales order changes after planning](sales-order-changes.md)).

Never planned, in either direction: a **Cancelled** line, and a line marked no purchase needed.
An order whose every line is one of those has nothing to plan at all.

## Steps

1. Open **[Project Sales Admin → Sales Orders](/scm/sales-orders)**. Find the orders you want,
   whatever their status - a **Completed** one can be planned.
2. Tick them in the list.
3. Click **Start** → **Plan selected (N)**. With nothing ticked the item is greyed out and says
   **Tick the sales orders to plan first.**; over the board's own limit it says how many the
   board takes at a time and how many you selected.
4. The board opens on that selection. Work each line the usual way (see
   [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md)), or use
   **Save all suggested (N)** to take the suggestions as composed.
5. Click **Confirm (N)**. The confirmation is what adopts a Completed order into planning;
   nothing has to be started separately first.

If the order is refused, the message names the reason: an order whose status is not **Open** or
**Completed** (a cancelled one) cannot be planned, and neither can an order whose every line is
cancelled or marked no purchase needed.

## The quantities on a delivered line

* The quantity a line asks the board for is the **ordered** quantity, not what is still owed. A
  line of 3 ordered and 3 delivered asks for 3, so a **Buy** on it raises an order back for all 3.
* The line panel's sub-heading counts that figure: it reads **N to plan · N decided**, and
  **Quantity needed** on the panel is the same number.
* The **Outstanding** column in the panel's **Contributing lines** table is a different figure on
  purpose: it is what is still owed to the customer. On a fully delivered line it reads 0 while
  the line still asks to be planned.
* A decision that sources a delivered unit from your own location records where it came from and
  holds no stock: the unit already shipped, so there is nothing left to hold. Only what is still
  owed is held.

## Empty states

* **No lines to plan on these sales orders** with **Every line is cancelled or marked no purchase
  needed.** - the selection genuinely has nothing to decide.
* **No lines in these dates** with **The selection holds N lines on other dates.** - the day
  window you are scrolled to is empty, the selection is not. Move the window.

## The Planned pill

**[Project Sales Admin → Sales Orders](/scm/sales-orders)** carries a **Planned** column after
**Status**, and the sales order's own page carries the same badge in the header beside its
status, identical whether you are viewing or editing:

| Reads | Meaning |
|---|---|
| **Planned** | Every line that can be planned is decided. |
| **Partly 2/3** | 2 of the 3 plannable lines are decided. |
| **Not planned** | Nothing on the order has been decided yet. |
| **-** | Nothing on the order can be planned: every line is cancelled or marked no purchase needed. |

It counts lines by the same rule the board uses, so an order that reads **Partly 2/3** opens a
board with one line left to decide. The column is not sortable and not filterable; the counts
are on the row itself.

## What gets created

* Nothing at all until you confirm. **Plan selected (N)** only opens the board, and saving a
  line records a draft decision.
* On confirm: the order's supply decision, plus an **ORDER** row on the order's Order Inquiry
  for every **Buy** - the order back for stock that already shipped. Purchasing sees it on
  **[Order Inquiries](/project-sales/order-inquiries)** exactly as it sees a Buy on an open
  order.
* The sales order's **Lines** tab then names that inquiry in its **Linked to** column, and the
  **Planned** pill moves to **Planned**.

## How you'll be notified

In-app toasts only, as each line saves and when the board confirms. There is no email or
WhatsApp for planning an order; purchasing picks the work up from Order Inquiries.

## See also

* [Buy and borrow decisions on Fulfilment Planning](local-buy-and-borrow-source.md) (also covers
  Undo last confirm, if you confirm the wrong thing)
* [Sales order changes after planning](sales-order-changes.md)
* [Upload the data a reorder plan is built from](upload-plan-data.md) (the sales order book and
  the Order Inquiry sheet behind these lines)
