# Supply Chain - Link a PO in AutoCount from Order Inquiries

Use this when an Order Inquiries row needs a purchase order and you want AutoCount itself to record
the link, not only the CRM. It is the same feature, popup and switch as
[Stock Debt](./stock-debt-link-to-po.md).

It only appears once an admin has switched on the AutoCount link setting (see
[Switching it on](#switching-it-on)). With it off, the three items below do not show.

## Where

* **[Procurement → Supply Chain → Order Inquiries](/project-sales/order-inquiries)**, the
  **Actions** menu, or a right-click on a row.

## Steps

1. Tick the rows you want to decide on. Tick rows of one product at a time.
2. Open **Actions** and choose one of:
   * **Link to PO... (n)** - give the rows a PO.
   * **Change PO... (n)** - move rows from the PO they have to another one.
   * **Unlink from PO... (n)** - take the PO off in AutoCount.
3. Or right-click a single row: the same three items appear for that row alone.
4. In the popup, each row has its own line: pick a PO line and a **Qty**. **Qty** starts at what
   the sales order line still needs, never more than what is free on the PO line. If you give less
   than the whole PO line, AutoCount splits the PO row for you.
5. Untick any line you do not want to send, then press the button at the bottom.

## What the count means

**n** is the number of ticked rows whose sales order line is already in AutoCount. When some are
not, it reads like **2 of 3**, and only the 2 are sent. An item is greyed with a reason when it
cannot run:

* **Not in AutoCount yet** - none of the ticked rows has its sales order line in AutoCount.
* **Tick rows of one product** - the ticked rows are for more than one product.

## What you see afterwards

Each line answers on its own:

* **Done** - AutoCount recorded it. The row shows the PO in its PO column at once. (This needs the
  Order Inquiry action permission. Without it, the PO appears after the next AutoCount sync.)
* **Refused** - AutoCount did not accept it. The reason is shown, nothing was changed, and you can
  press **Try again**.
* **Unknown** - AutoCount did not answer in time. Pressing retry first checks AutoCount for what
  actually happened, so the same change is never made twice.

## Renamed items

Two older items on the same menu were renamed so they are not confused with the above:

* **Recheck in AutoCount** (was **Link selected**) - re-runs the AutoCount step on ticked rows.
* **Remove link in CRM** (was **Unlink selected**) - removes the CRM link only. Nothing changes in
  AutoCount. Use **Unlink from PO...** to remove it in AutoCount.

## Switching it on

**[User Management → Settings](/user-management/settings)**, the switch **Link PO lines in
AutoCount (Stock Debt, Order Inquiries)**. It is off on a new installation, and one switch covers
both screens.

## Who can use it

* The **Link PO lines in AutoCount (Stock Debt, Order Inquiries)** permission (admins hold it).
  Without it, the three items do not show.

## What gets created

* In AutoCount: the PO line is linked to the sales order line, split when you give a partial
  quantity. AutoCount records who pressed the button.
* In the CRM: the row's PO column is updated from what AutoCount read back.

## See also

* [Link a PO to a sales order line from Stock Debt](./stock-debt-link-to-po.md)
* [Order inquiry documents](./order-inquiry-documents.md)
* [When a PO line got its S/O](./purchase-order-link-history.md)
