# Sample team - Process a sample request: answer the date, link the consignment

For whoever holds **Process sample requests**. A request goes through two stages: **Processing**
(Submitted, Processing, Customer confirmed) and **Delivery** (Delivered).

## 1. Start processing and answer the delivery date

1. Open the request (**Project Sales > Sample Requests**).
2. Click **Change to processing**.
3. Answer **Can we deliver by <requested date>?**:
   * **Yes, we can meet it**, or
   * **No, propose a new date**, then pick the **Proposed date** (today or later).
4. Optionally add a **Note**, for example *Stock from KL*. The salesperson sees it.
5. Click **Change to processing**.

The salesperson sees your answer on the request and in their list. They do not have to accept it.

You can't start processing without answering. The refusals are:

* *Say whether the requested delivery date can be met.*
* *Enter the date the sample team can deliver.*
* *The proposed date cannot be in the past.*

### Change the answer

While the request is Processing or Customer confirmed: gear menu, **Change date answer**, then
**Save**. Each change is added to the project's activity.

## 2. Link the consignment: that is the delivery

The AutoCount consignment (`CG-...`) is the sample delivery.

1. Gear menu, **Link consignment** (available from Processing onwards).
2. Search by CG number or debtor. The list shows only this company's consignments that are not voided.
3. Click **Link**.

The request becomes **Delivered**:

* **Delivered** date: the delivery date that order tracking recorded for that consignment
  (*Order Tracking*), else the consignment's own date (*consignment date*). A tracking date that
  arrives later replaces the consignment date on its own.
* **Return due** = delivered date + the loan period.
* **Consignment No** now shows the linked consignment. The free-text number in **Set
  consignment / PO no** is locked while a consignment is linked.

To fix a wrong link, run **Link consignment** again and pick the right one.

**Mark delivered** disappears once a consignment is linked. Without a consignment (for example a
board-only request), **Mark delivered** still works with a date you type.

If AutoCount voids the linked consignment, the request goes back to Customer confirmed (or
Processing) by itself and shows **Voided in AutoCount**. If AutoCount restores it, the request is
delivered again.

## See also

* [Track a sample request (salesperson)](../project-sales-rep/track-a-sample-request.md)
