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

## Undo last confirm

Read this when you pressed **Confirm** on the board and want it back, right after, before
anyone else acts on it.

### Where the entry is

Open the gear menu at the top of the board. Below **Undo all** (which only throws away
drafts, not anything already confirmed) there is one entry per order on the board whose newest
Confirm can still be undone, worded **Undo &lt;SO number&gt; confirm (rev &lt;N&gt;)** - for
example **Undo SO314593 confirm (rev 2)**. An order with nothing to undo (nothing confirmed yet)
simply has no entry.

### Walking back more than one Confirm

Undo can be pressed again after an undo. Each revision keeps its own record, so once the entry
above puts rev 2 back to rev 1, the gear menu now offers **Undo &lt;SO number&gt; confirm (rev
1)** - press it again and the order goes back to undecided. There's no limit beyond how many
revisions the order actually has; walk it back as far as it goes, one Confirm at a time.

### The countdown

Selecting the entry turns the board's **Confirm** button into a countdown reading
**Undoing in &lt;N&gt;s** with **Cancel** beside it, and the order number underneath so you can
see which order it's about to touch. The window length is the reversible window set in
**System Settings**. Pressing **Cancel** before it runs out puts the **Confirm** button straight
back and nothing on the board has changed. Pressing Escape does nothing - this is a deliberate
countdown, not a dialog, so it can't be dismissed by accident.

### What comes back

When the countdown runs out, the board puts everything back exactly as it was the moment before
you clicked Confirm: the lines go back to undecided (or to whatever their previous confirmed
revision was, if there was one), any drafts you had typed for those lines come back too, and the
purchase rows that Confirm had handed to purchasing are removed or restored to their earlier
state along with them. Each revision keeps its own record for as long as it exists, so once
you're back on an earlier revision, that one can be undone too (see "Walking back more than one
Confirm" above) - and once you confirm again, a fresh revision is minted that can be undone in
its own right.

### When the entry is greyed out

The entry stays visible but disabled, with the reason written underneath it, when purchasing has
already started acting on what that Confirm raised, or when something else changed the row since:

* **Purchasing linked a PO line** - someone in purchasing has manually linked one of the rows
  this Confirm raised to a purchase order line.
* **Purchasing marked a row actioned** - someone in purchasing has marked one of the rows as
  actioned.
* **A row changed since this confirm** - one of the rows this Confirm raised was written to by
  something else since (for example a later sales-order change), so undoing it would overwrite
  that other change.

Either way, the fix isn't to force the undo - ask purchasing to unlink the row first if it truly
needs undoing, or, if the mistake can be fixed going forward instead, leave the confirmed
revision alone and re-plan the line from here (decide it again and confirm on top of it).

An order's gear entry can look pressable and still be refused the moment you press it, if
purchasing linked or actioned a row in between opening the board and clicking the entry - the
board doesn't re-check every entry live. The reason shows in the toast that comes back.

### Reconstructed undo

Orders confirmed before 17 September 2026 predate the record depth-N undo above relies on, so
there's nothing to replay for them. For those, admins (not planners) see an extra kind of entry:
**Undo &lt;SO number&gt; confirm (rev &lt;N&gt;), reconstructed**, with a second line reading
**Saved drafts and row notes are not restored**. It puts the order back as closely as it can from what's still on the rows themselves,
but a few things genuinely can't come back: saved drafts, the note text a later change
overwrote, acknowledgement stamps, links purchasing has since removed by hand, and a
partly-linked shrink's pre-shrink quantity. Planners never see this entry - only superadmin and
admin roles do. It uses the same countdown and the same refusal reasons as an ordinary undo.
Purchasing is still told: the automatic email for a reconstructed undo carries the headline
**RECONSTRUCTED** instead of the usual **UNDONE**.

### Purchasing is told automatically

Every undo sends purchasing one email, **Order inquiry undone**, listing the sales order and
every row that went back or disappeared - the same way the handover email tells them about a
fresh Confirm. Nothing needs to be forwarded by hand. This automation can be turned off or its
recipients changed under **[System Management → Automation](/system-management/automation)**,
same as any other automated email.

### Not the same as Reset planning

**Reset planning**, on **[Project Sales Admin → Sales Orders](/scm/sales-orders)** (**Actions →
Reset planning**), is a different, larger action: it wipes every revision, every order inquiry
row, link and stock transfer the order has ever had, for repeating a UAT walkthrough from a
clean slate. Undo last confirm only ever steps back one Confirm, on one order, and only while it
is still fresh enough to reverse.

## See also

* [Plan a sales order nobody decided](plan-undecided-lines.md) (which lines reach this board,
  and the Planned pill on the Sales Orders list)
* [Sales order changes after planning](sales-order-changes.md) (Confirm/Amend on a changed line -
  the same Undo applies to that Confirm too)
* [Order inquiry handover email to purchasing](order-inquiry-handover-email.md) (what a fresh
  Confirm sends; undo sends its own "Order inquiry undone" email instead)
* [Manage suppliers](../procurement/manage-suppliers.md) (Country is set there)
* [Countries](../product/countries.md)
* [Run a reorder plan](run-a-reorder-plan.md)
