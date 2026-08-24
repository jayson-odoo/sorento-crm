# Project Sales Manager - Approve a purchase request or sponsorship form via email

When a project sales admin clicks **Send for approval** on a purchase request or sponsorship form, the system generates a **one-time approval link** and (if **Create link & send email** was chosen) emails it to the configured approver. As project sales manager, you receive that email and use the link to approve or reject without logging in to the CRM.

## What you receive

An email with the approval link. The link is **token-based**, **one-time use**, and **expires after 24 hours**. If it expires before you use it, ask the admin to click **Send for approval** again to issue a new one.

## Approving / rejecting


1. Click the link in the email. The token-protected approve page loads - you do **not** need to log in.
2. The page shows the request / form details (header, items, attachments, requester).
3. Decide:
   * **Approve** - confirms the request. The status flips to **Approved**. The rep who submitted is notified via WhatsApp through Respond.io.
   * **Reject** - sends the request back. The status flips to **Rejected**. The rep is notified, can edit, and the admin can re-issue the link.

## What happens after

* **Approved:** the request / form proceeds downstream (e.g. purchase requests are visible to purchasing for fulfilment).
* **Rejected:** the rep edits and re-submits, the admin reviews again and clicks **Change to pending approval** then **Send for approval** to issue a fresh link.

## If the link is missing or expired

* Ask the admin to open the request / form on the CRM and click **Send for approval** again. They can choose **Create link & send email** to mail you a new link, or **Create link only** to copy and send it through another channel.
* The **Approval link (one-time use)** shown in the dialog is interchangeable - you can open it from any browser.

## See also

* [Flow stock inquiry to purchasing](flow-stock-inquiry.md)
* [Project Sales Admin - Review and send a purchase request for approval](../project-sales-admin/review-purchase-request.md)
