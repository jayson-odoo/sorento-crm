# Supply Chain - Link a PO to a sales order line from Stock Debt

Use this when a sales order line in a Stock Debt snapshot is short and a purchase order already
has stock you want to give it: you link the PO to the line, and AutoCount records it.

This only appears once an admin has switched on **AutoCount links from Stock Debt** (see
[Switching it on](#switching-it-on)). Until then the drill works as before, with **Request CS
to reserve** only.

## Where

* **[Procurement → Supply Chain → Stock Debt](/project-sales/stock-debt)**, open a snapshot, then
  press a month cell (or the product) to open its lines.

## Steps

1. Tick the sales order lines you want to decide on (the checkbox at the start of each row).
2. Press **Decide (N)**. N is how many lines you ticked.
3. Choose **Link to PO…**.
4. In **Link to PO**, each ticked line has its own row:
   * **PO**: pick the purchase order. Only POs with stock still free for this product are
     listed. When one PO has two such lines, each shows its line number in brackets, e.g.
     **202608-S0040 (2)**.
   * **PO qty** and **Free** show the picked PO line's quantity and what is still free on it.
   * **Qty** starts at what the sales order line still needs, never more than **Free**.
5. Untick any row you do not want to send, then press **Link N lines**.

Each line then shows its own result:

* **Linked**: "SO… line … now covered by PO … (qty)."
* **Linked, location not moved**: the link stands but AutoCount kept the PO line at its old
  location. Press **Move to the sales order location**.
* **Not linked**: AutoCount did not accept it, with the reason. Nothing was changed.
* **Needs attention**: AutoCount stopped part way. Press **Resume** to finish it.

The **Now** column of the drill then shows the PO covering the line, e.g. **PO 202608-S0040
(10)**, without taking a new snapshot.

## What you cannot do (and why it is greyed)

* **Already covered by PO …**: the line is fully covered by POs already. It cannot be ticked in
  the popup, and **Link to PO…** is greyed when every ticked line is covered.
* **In another AutoCount book from this sales order**: a PO from a different AutoCount company
  book cannot be linked to this sales order.
* **Waiting for AutoCount**: AutoCount cannot do this yet. Today that is **Unlink from PO…**,
  **Move PO to another sales order…**, and linking a PO line's whole quantity.
* **Changes to AutoCount are switched off here**: AutoCount does not accept changes from this
  environment.
* **Linking the whole PO line: Waiting for AutoCount**: set **Qty** below the PO line's whole
  quantity.

## Switching it on

**[User Management → Settings](/user-management/settings)**, **AutoCount links from Stock Debt**.
It is off on a new installation. While it is off, **Decide** shows no PO actions at all and the
CRM refuses any link request. Switch it on only after the link has been tested end to end with
AutoCount.

## Who can use it

* The **Link PO lines from Stock Debt** permission (admins hold it). Without it, **Decide** shows
  no PO actions.

## What gets created

* In AutoCount: the PO line's quantity is reduced by **Qty**, and a new PO line of that quantity
  is added at the sales order line's location, linked to the sales order line.
* In the CRM: the PO lines are updated from what AutoCount read back, so the drill shows the link
  at once. The next AutoCount sync confirms it.

## See also

* [When a PO line got its S/O](./purchase-order-link-history.md)
* [Order inquiry reserve email](./order-inquiry-reserve-email.md)
