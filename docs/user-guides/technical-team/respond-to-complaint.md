# 7.1-Technical Team — Respond to a complaint

Use this flow when the technical team needs to write or update its response to an open complaint. You can save the response as an internal draft, or save **and** send it to the customer via Respond.io in one action.

## Where to find complaints

Open [**Complaint Management → Complaints**](/complaint-management/complaints). The page lists every complaint with its current status — **Open**, **Responded**, **Approved**, or **Rejected**.

Click a row to open the complaint detail page (`/complaint-management/complaints/{id}`).

## Step 1 — Open the response editor

On the complaint detail page click **[Edit technical team response](#guide_target=complaint-management.complaints.tech-team.edit-response)** in the top action bar.

A dialog opens with:

* A textarea pre-filled with the existing response (blank for first-time responses).
* A reminder: "Save updates the record only. Update & Reply saves your text and sends it to the contact."
* Two action buttons (described below).

## Step 2 — Write the response

* Plain text. Newlines are preserved when the message is sent to Respond.io.
* Keep the message customer-facing if you plan to **Update & Reply**.
* Empty responses are saved but won't be sent to Respond.io.

## Step 3 — Save or send

You have two options:

* **[Save only](#guide_target=complaint-management.complaints.tech-team.save-response)** — persists the response on the complaint record. No message is sent to the customer. The complaint stays in its current status. Use this when you're drafting internally.

* **[Update & Reply](#guide_target=complaint-management.complaints.tech-team.update-reply)** — saves the response **and** posts it to the customer's Respond.io thread. The complaint moves to **Responded**, which unlocks the **Approve** and **Reject** actions for whoever has those permissions.

  Disabled when the complaint has no `respond_inbox_url` (i.e. there is no linked Respond.io conversation). In that case you must use **Save only** and the salesperson can later forward the response manually.

## What happens after Update & Reply

* The customer sees the technical team's response in their Respond.io thread (WhatsApp / etc.).
* Status → **Responded**.
* The chat sidebar on the complaint detail page shows your message with a "sent" tick.
* The complaint is now eligible for review — see [Approve or reject a complaint](approve-or-reject-complaint.md).

## Permissions

* `complaint_management.complaints.edit` — needed for both **Save only** and **Update & Reply**.

## See also

* [Set Root Cause & Resolution and notify salesperson](set-root-cause-and-resolution.md)
* [Approve or reject a complaint](approve-or-reject-complaint.md)
