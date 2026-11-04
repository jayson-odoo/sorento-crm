# Supply Chain - When a PO line got its S/O

Read this when you want to know when a purchase order line was linked to the sales order shown in
its **S/O** column, what it was linked to before, or who placed an order inquiry on it.

## Where

* **[Procurement → Supply Chain → Purchase Orders](/scm/purchase-orders)**, open an order, then
  the **Lines** tab and the **History** tab.

## The S/O column

The **S/O** on a purchase order line comes from AutoCount: the purchase line records which sales
order it was raised for, and the AutoCount sync copies that onto the line. Nobody sets it in the
CRM.

When the sync has changed a line's S/O, a small clock icon sits next to the value. Click it:

* **Linked by AutoCount sync**, with **When** (Malaysia time) and **Was** (the S/O it replaced,
  or **Not linked** if the line had none before). A line that was split in AutoCount arrives as a
  new line already linked, so it reads **Was: Not linked**.
* **Unlinked by AutoCount sync** on a line showing a dash: AutoCount removed the link; **Was**
  names the S/O it used to carry.
* **Linked on or before** a date, with **Earlier history not recorded**: the line was already
  linked before the CRM started keeping this history (4 Nov 2026). The date is the earliest the
  CRM saw the link, so the real moment may be earlier.

A line with no icon has no recorded change.

AutoCount does not tell the CRM who changed a link in AutoCount, so the CRM can only say the sync
did it and when.

## The History tab

The **History** tab lists every S/O change on the order's lines, newest first, one row per change,
for example `BRW-NTC: S/O none → SO422492`. Staff edits to the order itself show here too. Anyone who
can open the purchase order sees its History tab.

## Who placed an order inquiry on a line

On the **Lines** tab, click a line's **Placed** figure. In the popup, the **Linked** column on an
order inquiry row shows who linked it and when, or **Auto** when the system linked it on its own.
SPO and Dedicated rows show a dash.
