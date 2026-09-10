# Supply Chain - Buy and borrow decisions on Fulfilment Planning

Read this when you're deciding a line on the Fulfilment Planning board: how to tell a **Local**
Buy from an overseas one, what happens to each on confirm, and how the **Add a borrow** dialog
shows you where a borrow would come from.

## Where

Open **[Supply Chain → Planning → Project Demand → Fulfilment Planning](/project-sales/fulfilment-planning)**.
The same board is also reachable from **Procurement → Supply Chain → Order Inquiries** once a
line has been raised there.

## The Local pill

A product is **Local** when the supplier it's bought from sits in Malaysia - the supplier
linked to the product directly, or if there is none, the supplier on its most recent purchase
order. Everything else (no known supplier, or a supplier outside Malaysia) is treated as
overseas.

* On the List view, a local line's **Suggested** cell reads its verdict followed by a **Local**
  badge, for example "Buy 50 Local". The **Decided** cell carries the same badge once the line
  is decided or confirmed. An overseas line shows no badge.
* Expand a row's **OPTIONS** table: the **Buy** row carries the same **Local** badge when the
  product is local. No other option row does.
* The **OPTIONS** table no longer shows a short reason line under each option - only the
  figures. Where a decision needs explaining, open the board's decision trail instead.

## What happens on confirm

Confirming a Buy works exactly as before - nothing new to click. The difference is what it
does afterwards:

* **A local Buy is recorded on the decision, same as any Buy, but raises nothing on
  [Order Inquiries](/project-sales/order-inquiries).** It does not reach purchasing's overseas
  list, and it does not count toward reorder demand for that product - the buyer places that
  order through their own local process instead.
* **An overseas Buy on the same order is raised as normal**, under its own Order Inquiry
  header.
* **A line that was already raised on Order Inquiries before its product became local is left
  exactly as it was** the next time the order is confirmed - it is not re-raised and it is not
  cancelled. Purchasing closes an old row like that by hand once it no longer applies.

## Add a borrow

Click **Add a borrow** on a line to open the borrow dialog (titled **Borrow for line N**). The
**Source** section is the same Location table the Grid view shows, not a separate summary:

**Location · Where · On hand · SO qty · SPO qty · Available · Available for Project · PO qty ·
Taken**

* Pick a source with the radio next to its **Location**. The first row carries a
  **Recommended** badge; a donor that shares your sales agent carries a **Same agent** badge
  instead (or as well).
* When a source is one particular donor line rather than plain free stock (for example,
  stock held against another sales order that can wait), its sales order and line number show
  under the location code, e.g. "SO371334 line 2" - not just a bare location.
* Expand a source row to see its sales-order ledger, the same as the Grid view's expanded
  Location row, so you can see which orders sit on it before you take from it. The current
  line's own rows in that ledger are marked **This line**.
* Type the **Quantity**; the sentence below it updates live, e.g. "After borrowing 50: BRW-NTC
  goes short by 284 - an Order Inquiry will be raised for BRW-NTC on confirm."
* **Reason** is required. Click **Add the borrow** to add it to the line's decision (still not
  saved until you save the line's decision), or **Cancel** to back out.
* If nothing has stock to spare for this item, the dialog reads **No donor holds this item**
  instead of a table.

## See also

* [Manage suppliers](../procurement/manage-suppliers.md) (Country is set there)
* [Countries](../product/countries.md)
* [Run a reorder plan](run-a-reorder-plan.md)
