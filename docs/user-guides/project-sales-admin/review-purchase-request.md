# Project Sales Admin — Review and send a purchase request for approval

Project sales reps submit purchase requests through the [portal](../project-sales-rep/portal-overview.md). They land in the system as **Draft** (still being edited by the rep) or **Pending approval** once the rep clicks **Submit**. As project sales admin, your job is to **review** the submitted request and send it for approval to the project sales manager.

## Where to find purchase requests

Open **[Procurement → Purchase Requests](/procurement-management/purchase-requests)** (URL: `/procurement-management/purchase-requests`). The page is titled **Purchase Requests**.

The DataGrid lists every purchase request. Filter by **Approval Status** to find the ones waiting on you. The full set of statuses is: **Draft**, **Pending approval**, **Approved**, **Rejected**.

## Review


1. Click a row to open the detail page (URL: `/procurement-management/purchase-requests/{id}`).
2. Read through the header (project / customer / contact), the **items** table (products, quantities, requested terms), the **attachments** section, and the conversation panel for any context messages from the rep.
3. If anything is missing or wrong, click **Edit** in the toolbar to amend, or use **Chat records** in the actions menu (`⋯`) to message the rep on Respond.io for clarification.

## Move to "Pending approval"

If the request is still in **Draft** when you receive it, click [**Change to pending approval**](/procurement-management/purchase-requests#guide_target=procurement.approvals.change-to-pending-approval-button) in the toolbar. This locks the request from rep edits and signals it's ready for the manager. A toast confirms: *"Status set to Pending approval"*.

## Send for approval

When the request is in **Pending approval**, click [**Send for approval**](/procurement-management/purchase-requests#guide_target=procurement.approvals.send-for-approval-button) in the toolbar.

* If your tenant has a **default approver** configured, the system **immediately** generates a one-time approval link and emails it to the configured approver. Toast: *"Approval link sent to {email}"*.
* If there is no default approver, the **Send for approval** dialog opens. Fill in:
  * **Choose approver (optional)** — pick a user from the dropdown to pre-fill their email, or leave it blank.
  * **Approver email** — required. Use the manager's email if they're not in the system.
* Then click one of:
  * [**Create link only**](/procurement-management/purchase-requests#guide_target=procurement.approvals.create-link-only-button) — generates the link without sending an email. Useful when you want to share the link via another channel (e.g. paste into chat).
  * [**Create link & send email**](/procurement-management/purchase-requests#guide_target=procurement.approvals.create-link-and-send-button) — generates the link **and** emails it to the approver address.

After the link is created, the dialog shows **Approval link (one-time use)** with a copy icon. Click **Done** to close.

The link is **token-based** and **one-time-use** — the manager can open it without logging in, and it expires after 24 hours.

## What the manager sees

Opening the emailed link takes the manager to a token-protected approve page where they can **Approve** or **Reject** the request. See the [project sales manager guide](../project-sales-manager/approve-via-email.md) for the manager's side.

## After approval / rejection

* **Approved:** the status flips to **Approved** and a notification is sent to the rep through Respond.io (WhatsApp). The request is now actionable downstream (purchasing, etc.).
* **Rejected:** the status flips to **Rejected**. The rep is notified and can edit and re-submit. You can re-issue an approval link by clicking **Change to pending approval** again, then **Send for approval**.

## Other actions on the toolbar

* **Edit** — open the form to amend any field.
* **Delete** — delete the request (destructive; confirmation required).
* **Actions menu (**`**⋯**`**)**:
  * **Copy view link** — a read-only link you can share without giving full access.
  * **Export to Excel** — exports the request and items to Excel.
  * **Chat records** — opens the Respond.io conversation panel.
  * **Update & Reply** — composes a reply on Respond.io with the saved message text.

## See also

* [Review and send a sponsorship form for approval](review-sponsorship-form.md) — same shape, separate module
* [Project Sales Manager — Approve via email link](../project-sales-manager/approve-via-email.md)
* [Project Sales Rep — Portal overview](../project-sales-rep/portal-overview.md)
