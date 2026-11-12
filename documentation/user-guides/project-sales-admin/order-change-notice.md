# Project Sales Admin - Raise and process an Order Change Notice

Use an Order Change Notice when an order has already been received and something about it changes: the customer wants it earlier, later, swapped for another item, or cut back or cancelled. The notice records the change, gets it checked and approved, and tells Customer Service to carry it out. It follows the same path as a purchase request: salesperson, sales admin, management, Customer Service.

> A notice is a record with an approval and a clock. It never changes the sales order, the customer PO or AutoCount. Customer Service makes the actual change after approval.

## Where to find it

Open **Project Sales Admin > Order Change Notices**, after **Sponsorship Forms**. The page lists every notice you may see. Click a row to open it.

You see all notices of your company, or only the ones you raised or are named on (as sales in charge or C.S. in charge), depending on your role.

## Types of change

Pick one **Type of change**. Each type shows its risk and a short guide text on the form.

| Type | Risk | Use it for |
|------|------|-----------|
| **Cancellation** | Highest | Cancelling an item or the order. A cut in quantity is also filed as a Cancellation. |
| **Exchange** | High | Swapping an item for another, including stock already delivered. |
| **Advance** | Low | Delivery wanted earlier. |
| **Delay** | Low | Delivery wanted later. |

The risk is shown for information. It does not change who approves or how long each step takes.

## Steps - raise a notice (salesperson)

1. Open **Project Sales Admin > Order Change Notices** and click **Create**.
2. Fill in the header:
   * **Customer Name** (required) - search and pick the customer.
   * **Customer PO No.** (required) - type it, for example `XT04/3871 (R1)` for a revised PO.
   * **SO No.** - type it.
   * **Registered project (optional)** - search a project by code or title. It becomes required only when an admin has switched on **Order change notices need a registered project**.
   * **C.S. Incharge** and **Sales Incharge** - choose a person each.
   * **Type of change** (required) - Advance, Exchange, Cancellation or Delay.
   * **Description** - say what is changing and why.
3. Under **Line items**, click **Add row** for each affected item and fill in **Product**, **Qty before**, **Qty after**, **Date before**, **Date after**, **Delivered** and **Remark**. Delivered is for information; nothing is blocked if goods have already been delivered. Add at least one line to submit.
4. Attach supporting files, such as the revised customer PO.
5. Click **Save as draft** to keep working later, or **Submit** to send it on. Dates read dd/mm/yyyy.

Example: Customer A, PO `XT04/3871 (R1)`, type Exchange, one line for `ABC123-RL` with Qty before 842 and Qty after 842, and the replacement named in the Remark.

## Steps - the approval path

| Who | Does what | Buttons |
|-----|-----------|---------|
| Salesperson | Raises and submits | **Submit** |
| Sales admin | Checks it, then passes it on or returns it to the raiser | **Send for approval**, **Send back** (a reason is required) |
| Management | Decides, with remarks if rejecting | **Approve**, **Reject** (remarks required) |
| Customer Service | Carries out the change, may add a comment, closes it | **Mark done** (the **Customer Service comment (optional)** box is in its dialog) |

* **Sent back or rejected:** the notice goes back to the raiser, who opens **Edit**, amends and submits again.
* **Approved:** the notice is locked. To change it, open the actions menu (**Notice actions**) and choose **Revise**, say what changed and why, and it reopens as a draft that goes through the path again.
* **Void:** from the same menu, **Void** ends a notice that is still open. A reason is required. A voided notice cannot be approved or rejected afterwards.
* **Undo:** after you press a button, the action is held for a short time. While it is held you can cancel it. Once it has gone through, **Undo last action** in the menu appears if the last step can still be reversed.

Status reads **Draft**, **Submitted**, **Pending approval**, **Approved**, **Rejected**, **Done** or **Voided**. The default approver is set in Settings under **Default approver (order change notices)**.

## How long each step may take

Each step has a time limit, shown on the **SLA** tab of the notice:

| Step | Time |
|------|------|
| Sales admin check | 24 hours |
| Management approval | 72 hours, then the Director for 24 hours |
| Customer Service carries it out | starts when it is approved |

A step that runs over escalates as for purchase requests.

## Tabs on the notice

* **Details** - the form, the line items, attachments, the **Customer Service comment** and the sign-off (**Decision**, **Name**, **Date**, **Remarks**).
* **Conversation** - comments between the people on the notice.
* **SLA** - the steps of this notice and their clocks.
* **History** - every action: who, when, and what moved.

## What this does to a project sales order

An amendment to a published project sales order needs an approved notice before it can publish. The notice is what gets approved; the amendment is what then changes the sales order.

When you create an amendment, the **Order change notice (optional)** field lets you:

* leave it on **Draft a new notice from this change**, which prepares a new notice for you from the change, or
* pick an existing notice of the same project instead, so one change has one notice. Notices that are pending approval, voided, done, or already used by another amendment are not offered. Picking an approved notice sends it back to draft so the change is approved again before it publishes.

Open the notice, check it and **Submit**. A rejected notice keeps the amendment from publishing until it is amended and approved. A notice made from an amendment shows its project, SO and PO read-only.

## Who can do what

| Permission | Lets you |
|------------|----------|
| View all | See every notice of the company |
| View own | See notices you raised or are named on |
| Create | Raise a notice |
| Edit | Send for approval, send back |
| Mark done | Mark done as Customer Service |
| Approve | Approve or reject |
| Report | Use the notice in reports |

If a button is missing, check the status and your role. Ask an admin to change the role.

## How you'll be notified

Only the person who has something to do is told: the next step's owner when a step starts, the same person again when it runs late, and the raiser when the notice is rejected, approved, done or voided. Channels and wording are the same as for purchase requests.

## See also

* [Review and send a purchase request for approval](review-purchase-request.md)
* [Review and send a sponsorship form for approval](review-sponsorship-form.md)
* [Purchase request and sponsorship form lifecycle](purchase-request-lifecycle-and-next-actions.md)
