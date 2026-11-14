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
 3. In the **Request** section, choose the **Currency** (required). Optionally set **Needed by**, a **Default location** and a **Reason**.
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
2. A value you changed shows what the requester submitted, for example "was 10", under it.
3. Click **Approve**. A popup titled with the request number lists **Your changes**, with an optional **Note**. Click **Approve** again to confirm, or **Back** to leave.
4. To send it back, click **Reject**. A **Reason** is required. The requester edits it and submits again, starting from level 1.

You can never approve your own request. If every line is at 0 you cannot approve; reject it instead. After the last level approves, lines with a quantity go to purchasing and lines at 0 are cancelled.

## What purchasing sees

* A request appears in **Order Inquiries** only after the last approval. Before that (draft, waiting for approval, rejected) purchasing does not see it in the list, counts, exports or notifications.
* On final approval, purchasing gets one notification titled with the request number, for example "Order request OR-2611-0001".
* The list has a **Type** column and a **Type** filter. These requests read **Order request**, and **S/O no** shows "-".
* The page has the same tabs as any order inquiry. **General** adds a **Request** card and an **Approval** card. **Lines** shows unit price, total, location, photos and any "was ..." values.
* Purchasing works it as usual: **Acknowledge**, reject a single line, and link a purchase order.

## Revise after approval (requester)

Until purchasing acknowledges a line, the request has a **Revise** button. It goes back to draft and leaves purchasing's list. Change what you need and **Submit**; approval runs again from level 1. Once any line is acknowledged, **Revise** is no longer offered.

## Who sees prices

Unit price and total are visible to the requester, the approvers (also after they have approved) and users with cost access. Everyone else does not see them, including in the **History** tab.

## History

The **History** tab records the submit, each approval, every change an approver made (old value to new value, who and when), a reject with its reason, a revise, and the final raise to purchasing.

## What gets created

* One order inquiry with its own monthly number, `OR-` instead of `OI-` (for example `OR-2611-0001`), type **Order request**, no sales order. Order requests count separately from sales-order inquiries, so the two series never skip a number for each other.
* The requester's submitted quantity and price are kept on each line next to the approver's values.

## How you'll be notified

* The approver team of the current level is notified when a request is submitted or reaches their level.
* Purchasing gets the notification once, on the last approval.

## See also

* [Order inquiries: the Documents view and the OI detail page](order-inquiry-documents.md)
* [Form SLA Configuration](../sla/form-sla-configuration.md)
