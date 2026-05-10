# Project Sales Admin — Review and send a sponsorship form for approval

Project sales reps submit sponsorship forms through the [portal](../project-sales-rep/portal-overview.md). They land in the system as **Draft** (still being edited) or **Pending approval** once the rep clicks **Submit**. As project sales admin, your job is to **review** the submission and send it for approval to the project sales manager.

> Sponsorship forms share the same review-and-approval flow and the same detail UI as purchase requests — only the entry point and the document type differ. If you've used the [purchase-request flow](review-purchase-request.md), this will look identical.

## Where to find sponsorship forms

Open **[Procurement → Sponsorship Forms](/procurement-management/sponsorship-forms)** (URL: `/procurement-management/sponsorship-forms`). The page is titled **Sponsorship Forms**.

Filter by **Approval Status**. Statuses: **Draft**, **Pending approval**, **Approved**, **Rejected**.

## Review


1. Click a row to open the detail page (URL: `/procurement-management/sponsorship-forms/{id}`).
2. Review the header (project / customer / contact), the **items** table (sponsored products / amounts), the **attachments** section, and the conversation panel for any messages from the rep.
3. If anything is missing or wrong, click **Edit** in the toolbar, or use **Chat records** in the actions menu (`⋯`) to message the rep.

## Move to "Pending approval"

If the form is still in **Draft**, click [**Change to pending approval**](/procurement-management/sponsorship-forms?guide_target=procurement.approvals.change-to-pending-approval-button) in the toolbar. Toast: *"Status set to Pending approval"*.

## Send for approval

When the form is in **Pending approval**, click [**Send for approval**](/procurement-management/sponsorship-forms?guide_target=procurement.approvals.send-for-approval-button) in the toolbar.

* **With a configured default approver:** the system immediately generates the one-time approval link and emails it. Toast: *"Approval link sent to {email}"*.
* **Without a default approver:** the **Send for approval** dialog opens.
  * **Choose approver (optional)** — pick a user from the dropdown to pre-fill, or leave blank.
  * **Approver email** — required.
  * Click **Create link only** (link only, no email) or **Create link & send email** (link + email to the approver).
* After the link is created, the dialog shows **Approval link (one-time use)** with a copy icon — click **Done** to close.

The link is token-based, one-time use, and expires after 24 hours.

## After approval / rejection

* **Approved:** status flips to **Approved**. The rep is notified through Respond.io (WhatsApp).
* **Rejected:** status flips to **Rejected**. The rep is notified and can edit and re-submit. You can re-issue an approval link by clicking **Change to pending approval** again, then **Send for approval**.

## Other actions on the toolbar

* **Edit** — amend any field.
* **Delete** — destructive, confirmation required.
* **Actions menu (**`**⋯**`**)**: **Copy view link**, **Export to Excel**, **Chat records**, **Update & Reply**.

## See also

* [Review and send a purchase request for approval](review-purchase-request.md)
* [Project Sales Manager — Approve via email link](../project-sales-manager/approve-via-email.md)
