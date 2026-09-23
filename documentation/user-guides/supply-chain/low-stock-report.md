# Supply Chain - Low stock report

Use this to get a workbook of every product below its reorder level, or the whole plan's
shortage book, either from a reorder plan or by asking the WhatsApp bot.

## Where

From a reorder plan (see [Run a reorder plan](run-a-reorder-plan.md)), open the **Actions**
menu on the Lines tab toolbar and pick **Low stock report Excel**, directly under **Order
sheet Excel**.

On WhatsApp, ask the bot for it directly - "low stock report", "low stock", "reorder
report", "stock below level", or "what needs reordering" all work. Add a warehouse code, a
product code, or a date window to the same message to scope the plan.

## What the workbook shows

The workbook carries two sheets:

* **Low stock** - only products currently below their raw reorder level.
* **All** - the rest of the book. **All prints exactly the rows the plan's Lines tab shows** -
  a covered product whose net sits above its own reorder level is left off both sheets, the
  same as the list (see [Run a reorder plan](run-a-reorder-plan.md#filters)). **Low stock**
  stays a subset of whatever **All** prints.

Both sheets share sixteen columns, sorted by category then item code: **Item code**,
**Description**, **Category**, **BRW on hand**, **Reorder level**, **Reorder qty**,
**Suggested qty**, **Suggestion**, **Order qty**, **Dealer o/s**, **Supplier**, **BRW PO
qty**, **BRW incoming qty**, **Last in qty**, **Last in date**, **Remarks**.

* **Description** and **Category** come from the product master at the moment of export, not
  from the frozen plan.
* **BRW incoming qty** prints one "container - quantity" line per open shipment, or the bare
  quantity when a shipment names no container - the SPO number itself is not shown. **BRW PO
  qty** still names each purchase order number.
* **Last in qty** reads the newest shipping order line for the product, received or not - the
  same line the chatbot's "last in" answer names. It prints one "container - quantity" line,
  or the bare quantity when that line names no container - the SPO number itself is not
  shown. It is blank when the product has no shipping order line at all.
* **Last in date** is that same line's expected delivery date, or its issue date when it has
  none.
* **Supplier** is dropped from both sheets entirely (not left blank) when the report is sent
  to a WhatsApp contact who does not hold the purchase-order supplier detail (see Access,
  below).

## Getting the file

### From a reorder plan

Same **My Downloads** flow as the order sheet: a toast reads "Preparing the low stock report -
it will appear in My Downloads." while the workbook builds in the background.

* The header's download icon (**My downloads**) picks up a badge counting sheets still
  preparing.
* Open the drawer to watch the row move from **Queued** to **Preparing** to **Ready**, then
  click it to download.
* If more than 5,000 rows would land on the **All** sheet, the export is refused up front
  ("Narrow the plan first") before anything starts preparing.

### Over WhatsApp

The bot always runs a **brand-new plan** for what you ask, never the plan currently open on
screen, so the figures reflect the book right now. If the workbook finishes quickly, it
arrives in the same reply; otherwise the bot says it is preparing and pushes the file
separately, over WhatsApp, once it is ready.

## Access

Asking for the low stock report over WhatsApp needs a per-contact grant. Open the contact, go
to **Access**, and on the **Field reveals** card tick **Low stock report over chat**. Without
it, the bot answers that the low stock report is not enabled for the account and nothing is
built. A separate grant, **Purchase orders → supplier**, controls whether the **Supplier**
column is included; without it the column is left out of both sheets rather than shown blank.

Getting the report from a reorder plan's **Actions** menu needs no separate grant beyond
being able to open the plan itself.

## See also

* [Run a reorder plan](run-a-reorder-plan.md)
* [Print the order summary](print-the-order-summary.md)
* [Chatbot - outstanding report (sales order backlog and delivery order outstanding)](../system-management/chatbot-outstanding-report.md)
* [Chatbot - "last purchase cost" answer](../system-management/chatbot-last-purchase-cost.md)
