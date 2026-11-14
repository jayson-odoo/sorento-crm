# Supply Chain - Order requests

Use this when you need stock replenished for spare parts and there is no sales order behind it. You raise an **Order request**, one or more approvers check it, and only then does purchasing see it in **Order Inquiries** and work it like any other order inquiry.

An order request is not customer demand. It does not change committed stock or the reorder suggestions. Once purchasing raises a purchase order for it, that order counts as incoming stock like any other.

## Raise a request (requester)

Where you find it depends on your role, the same way as Purchase Requests:

* **Procurement > Supply Chain > Order Requests** shows when your role has **View Order Requests**. Give it to approvers and to staff who raise requests; they still see only their own requests and the ones they approve.
* Salespeople who may raise requests (**Create Order Requests**) find **Order Requests** under **MY REQUESTS**.

To raise a request you need **Create Order Requests**.

1. Open **Order Requests** (under **Procurement > Supply Chain**, or under **MY REQUESTS**).
2. Click **Create**. The page opens as **New Order Request**.
3. In the **Request** section, choose the **Currency** (required). Optionally set a **Delivery date** (each new line starts on it; a line can take its own in the **Delivery date** column), a **Default location** and a **Reason**.
4. In the **Products** section, search for a product by code or name (for example ZZX-100). Only products from the catalogue can be added.
5. The **Description** starts as the product's name; change it if purchasing needs more detail. Purchasing sees your description on the line.
6. Check the **Location** on the line. It starts from the default location and can differ per line.
7. Enter **Qty** and **Unit price**. The line **Total** and the request total are worked out for you, in the request currency.
8. Click **Add product** for more lines. The bin icon removes a line.
9. Click the arrow at the start of a line to see the stock for that product. It is information only and never limits the quantity you ask for.
10. Each line with a product has a paperclip for photos, also on a new request. Photos added before the first save are uploaded when you save.
11. Click **Save as draft** to keep working later, or **Submit** to send it for approval. Either way you land on the request's own page. The request gets its own number, for example `OR-2611-0001`.

On **Submit** the page tells you next to the field what is missing: the currency, at least one product, a quantity above 0 on every line, a price that is not negative, and a location. If no approval level has been set up yet, the request is refused with a plain message; ask your admin (see "Set up the approval levels" below).

### Draft, edit and delete

* A draft has **Delete draft**, **Edit** and **Submit** at the top of its page. **Edit** opens the same form as **Create**.
* **Delete draft** starts a countdown with a **Cancel** button. Cancel inside the window and nothing is deleted. Otherwise the draft is removed when the countdown ends, even if you close the tab.
* A rejected request can be edited and submitted again in the same way.
* While a request is waiting for approval you can still **Edit** it. Saving sends it back to level 1, and **History** records the change.

## Set up the approval levels (admin)

Approval levels are set on **SLA Management > Form SLA Configuration**, using the form type **Order Request**. Each level is one stage, and each stage names the approver team. Requests go through the stages in order. See [Form SLA Configuration](../sla/form-sla-configuration.md).

## Who acts next (SLA Tracking)

While a request waits for approval, its page shows who must decide it:

* The **SLA Tracking** tab lists the open approval stage: the **Stage**, who it is **Assigned To** and when it is due. Click a row for its full timeline.
* If the stage was escalated or its deadline extended, a banner above the tabs says so and names who holds it now.
* When no stage is open (a draft, or once the request is approved or rejected) the tab says so. The **History** tab keeps every decision.

The requester and the approvers see this; other users do not.

## Approve or reject (approver)

The approver team of the current level is notified; the notification opens the request. You can also open it from **Procurement > Supply Chain > Order Requests**, which lists the requests waiting for you and the ones you have decided on. The request page has **Lines**, **General**, **History** and **SLA Tracking** tabs and the previous / next arrows. Go to the **Lines** tab; it shows the **Product code** and the **Description** in separate columns.

1. Where needed, change the **Qty** (0 drops the line), the **Unit price**, or add or remove photos. You cannot add or remove lines.
2. A line you changed shows its **History** icon beside **Qty** in colour (it stays grey on lines nobody changed). Click it to see each change, old value to new value, who and when.
3. Click **Approve**. A popup titled with the request number lists **Your changes**, with an optional **Note**. Click **Approve** again to confirm, or **Back** to leave.
4. To send it back, click **Reject**. A **Reason** is required. The requester edits it and submits again, starting from level 1.

You can never approve your own request. If every line is at 0 you cannot approve; reject it instead. After the last level approves, lines with a quantity go to purchasing and lines at 0 are cancelled.

### A request raised by an approver

If you are on the team of the last approval level (or an admin), a request you submit needs no approval: it goes straight to purchasing, gets its order inquiry number and sends purchasing the email, the same as a request the last level has just approved.

## What purchasing sees

* A request appears in **Order Inquiries** only after the last approval. Before that (draft, waiting for approval, rejected) purchasing does not see it in the list, counts, exports or notifications.
* On final approval the request gets an order inquiry number, for example `OI-2611-0021`, and purchasing gets one notification and the order inquiry email, the same email a confirmed sales order sends. Its subject reads `OI: <location> @ OR-2611-0001`, and the header row reads **OR NO**, **OR DATE**, **REQUESTER** and **REASON** instead of the sales order fields. Purchasing's list and the order inquiry page show the `OI-` number; the request page keeps its `OR-` number.
* On the request page, each line's **OI** column shows that number; click it to open the order inquiry at that line. On the order inquiry page, the line under the number says **Order request OR-...**; click it to go back to the request.
* The list has a **Type** column and a **Type** filter. These requests read **Order request**, and **S/O no** shows "-".
* The page has the same tabs as any order inquiry. **General** adds a **Request** card and an **Approval** card. **Lines** shows the approved quantity only (not what the requester first asked for), with unit price, total, location, delivery date and photos. A quantity changed after approval shows "Was N" beside it, with the old and new figures behind it, as on a sales order line.
* Purchasing works it as usual: **Acknowledge**, reject a single line, and link a purchase order.

## Revise after approval (requester or approver)

An approved request has a **Revise** button, also after purchasing has started on it. It opens the same form as **Create**: change a line's **Qty**, **Product** or **Delivery date**, add a line or remove one (prices, location and the request fields stay as approved). Save, then click **Submit**; approval runs again from level 1. If you are on the last level's team, your revision applies as soon as you submit it.

While the revision waits, purchasing keeps the request as it was approved, and every line you changed reads **Waiting for CS** on the order inquiry, exactly like a sales order line that changed: purchasing cannot confirm that line until the change is approved.

When the last level approves the change:

* Each changed line is updated on the order inquiry (quantity, product, delivery date), and purchasing gets the same order inquiry email a sales order change sends, old to new. A line purchasing had already acknowledged goes back to **To order** for them to confirm again. A removed line, or one set to 0, is cancelled; an added line goes to purchasing as a new line.
* Lines you did not change stay exactly as they were.
* The order inquiry number stays the same.

## Who sees prices

Unit price and total are visible to the requester, the approvers (also after they have approved) and users with cost access. Everyone else does not see them, including in the **History** tab.

## History

The **History** tab on the request page shows the whole life of the request: the submit, each approval, every change the requester or an approver made (old value to new value, who and when), a reject with its reason, a revise, the raise to purchasing, and what purchasing did after that. The **History** icon beside a line's **Qty** opens the same history for that one line.

On the order inquiry page, purchasing sees only what happened from the raise onwards: the raise, their own actions, and any change approved after that. What the requester and approvers did before the approval stays on the request page.

## What gets created

* One record with two numbers: the request's own monthly `OR-` number (for example `OR-2611-0001`) from the start, and an `OI-` order inquiry number from the final approval, taken from the same series as sales-order inquiries. Type **Order request**, no sales order.
* The requester's submitted quantity and price are kept on each line next to the approver's values.

## How you'll be notified

* The approver team of the current level is notified when a request is submitted or reaches their level.
* Purchasing gets the notification and the order inquiry email on the last approval (or when an approver raises the request), and the email again only when an approved line changes through **Revise**.

## See also

* [Order inquiries: the Documents view and the OI detail page](order-inquiry-documents.md)
* [Form SLA Configuration](../sla/form-sla-configuration.md)
