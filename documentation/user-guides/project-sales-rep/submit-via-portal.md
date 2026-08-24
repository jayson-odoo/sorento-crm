# Project Sales Rep - Submit a complaint, stock inquiry, purchase request, or sponsorship form

This guide walks you through filing a new submission from the portal. The four submission types share the same form shape, so the steps below apply to all of them - only the specific fields differ.

> **Before you start:** make sure you can reach the portal dashboard - see [Portal overview](portal-overview.md) for how to get the link via WhatsApp and verify with OTP.

## Open a new submission


1. On the `**/portal**` dashboard, switch the **Submission type** combobox to the type you want: **Stock Inquiry**, **Complaint**, **Purchase Request**, or **Sponsorship Form**.
2. Click the **New {Type}** button (e.g. *New Complaint*). The form opens at `/portal/{type}/new`.

## Fill in the form

The form is split into sections (some only show for certain types):

* **Header** - project / customer / contact references and notes.
* **Items** - the product table. Add a row per product, set the quantity, and any per-line fields shown.
* **Attachments** - photos, drawings, supplier quotes, etc.

Type into each field. Required fields are marked. The form auto-saves nothing - see **Save as draft** below to keep your progress.

## AI Extract (complaint only)

Complaints support an **AI Extract** shortcut to pre-fill the form from a photo, screenshot, or PDF.


1. Tap the **AI Extract** button.
2. The **AI Extract** dialog opens. Either:
   * Drop your file(s) into the drop zone.
   * Click **Choose files** to browse.
   * Click **Paste from clipboard** if you copied a screenshot.
3. Click **Extract**. The system sends the file to our backend, which uses an LLM to read the file and propose values for each field.
4. Review the proposed values and click **Confirm and prefill** to apply them. The form fills in; you can still edit any field before saving or submitting.

If the upload doesn't return useful values, dismiss the dialog and fill the form manually.

## Save as draft

Click **Save as draft** at the bottom of the form. Toast: *"Draft saved."* The submission keeps the **Draft** status - visible to you on the dashboard, not yet visible to project sales admin / manager / purchasing.

You can re-open the draft, edit it, and save again as many times as needed.

## Submit

When the form is ready, click **Submit**. A confirmation dialog appears (*"Submit this {type}?"*). Click **Submit** to confirm. Toast: *"Submitted."*

Once submitted, the submission **becomes read-only**. You can no longer edit fields or attachments. The status changes depending on the type:

* **Stock Inquiry** → **Pending project sales** (waiting on the project sales manager to flow it to purchasing or reject it).
* **Purchase Request** → **Pending approval** (waiting on the project sales admin to send it for approval).
* **Sponsorship Form** → **Pending approval** (same flow as purchase request).
* **Complaint** → **New** (waiting on the technical / complaint-handling team).

If you spot a mistake after submitting, you'll need to wait for the relevant team to **reject** the submission. Once it's rejected the form unlocks and you can edit and re-submit.

## Cancel

The **Cancel** button discards unsaved edits in the current session and returns you to the dashboard. It does **not** delete an existing draft.

## Delete a draft

To delete a draft you no longer need, open it from the dashboard and use the delete action. The **Delete this draft?** dialog confirms. Toast: *"Draft deleted."*

## How you'll be notified

All notifications come on **WhatsApp** through Respond.io to your registered number - there is no in-portal inbox.

| Submission | You receive a WhatsApp when… |
|----|----|
| **Complaint** | The technical team posts a response on the complaint. |
| **Stock Inquiry** | The project sales manager flows it to purchasing **or** rejects it; **and** when purchasing posts a response. |
| **Purchase Request** | The project sales manager **approves** it (or rejects it). |
| **Sponsorship Form** | The project sales manager **approves** it (or rejects it). |

The WhatsApp message contains a link back to the portal so you can open the submission and read the latest details.

## Editing after a rejection

If a submission is rejected, the form is unlocked. Open it from the dashboard, fix what needs fixing, **Save as draft** if you need to think about it, and **Submit** again when ready. The cycle repeats until it's approved (PR / sponsorship), flowed to purchasing (stock inquiry), or responded to (complaint).

## See also

* [Portal overview](portal-overview.md)
* [Project Sales Admin - Review a purchase request](../project-sales-admin/review-purchase-request.md)
* [Project Sales Manager - Flow stock inquiry to purchasing](../project-sales-manager/flow-stock-inquiry.md)
