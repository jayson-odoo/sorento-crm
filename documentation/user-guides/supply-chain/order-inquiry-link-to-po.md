# Supply Chain - Link a PO in AutoCount from Order Inquiries

Use this when an Order Inquiries row needs a purchase order and you want AutoCount itself to record
the link, not only the CRM. It is the same feature, popup and switch as
[Stock Debt](./stock-debt-link-to-po.md).

It only appears once an admin has switched on the AutoCount link setting (see
[Switching it on](#switching-it-on)). With it off, **Link PO...** links in the CRM only.

## Where

* **[Procurement → Supply Chain → Order Inquiries](/project-sales/order-inquiries)**, the
  **Actions** menu, or a right-click on a row.

## Steps

1. Tick the rows you want to link. Rows of different products can be ticked together.
2. Open **Actions** and choose **Link PO... (n)**, or right-click a single row and choose
   **Link PO...**. On an Order Inquiry document the same item is under the gear.
3. The **Link PO** popup has one row per sales order line:
   * A line with no PO yet: pick a PO line and a **Qty**. Only PO lines of that line's own product
     are offered. **Qty** starts at what the sales order line still needs, never more than what is
     free on the PO line. If you give less than the whole PO line, AutoCount splits the PO row for
     you. When no PO line of that product has stock free, the row says so; the other rows still
     work.
   * A line that already has a PO: its **Action** is **Keep**, **Unlink** or **Change to** another
     PO line of the same product.
4. Untick any line you do not want to send, then press **Save**.

## What the count means

**n** is the number of ticked rows whose sales order line is already in AutoCount. When some are
not, it reads like **2 of 3**, and only the 2 are sent. The other line still shows in the popup as its own row,
marked **Not in AutoCount yet**, with nothing to pick for it. The item is greyed with
**Not in AutoCount yet** when none of the ticked rows has its sales order line in AutoCount.

## What you see afterwards

Each line answers on its own:

* **Done** - AutoCount recorded it. The row shows the PO in its PO column at once. (This needs the
  Order Inquiry action permission. Without it, the PO appears after the next AutoCount sync.)
* **Not linked** - AutoCount did not accept it. The plain reason is shown (for example, the PO is
  not in AutoCount), nothing was changed, and you can press **Try again**.
* **Unknown** - AutoCount did not answer in time. Pressing retry first checks AutoCount for what
  actually happened, so the same change is never made twice.

## Renamed items

Two older items on the same menu were renamed so they are not confused with the above:

* **Recheck in AutoCount** (was **Link selected**) - re-runs the AutoCount step on ticked rows.
* **Remove link in CRM** (was **Unlink selected**) - removes the CRM link only. Nothing changes in
  AutoCount. Use **Link PO...** and set the line's **Action** to **Unlink** to remove it in AutoCount.

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
