# Project Sales Rep - Submit a complaint, stock inquiry, purchase request, sponsorship form, or price tag request

This guide walks you through filing a new submission from the portal. Stock Inquiry, Complaint, Purchase Request and Sponsorship Form share the same form shape, so the steps below apply to all four - only the specific fields differ. Price Tag Request (shown only if your account has been granted it) has a different shape - it opens as four sections instead - see [Price Tag Request](#price-tag-request) further down.

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

## Duplicate an existing submission

You don't have to start from scratch. From the dashboard, long-press (or right-click) a card and choose **Duplicate** from the preview, or open a submission and choose **Duplicate** from its gear menu. A new draft opens with every field and line copied from the source; attachments are never copied. See [Portal overview](portal-overview.md#duplicate-an-existing-submission) for the full walkthrough.

## Price Tag Request

Price Tag Request is only shown on the **Submission type** combobox if your account has been granted it. Its form opens as four sections, top to bottom, instead of the Header / Items / Attachments shape above:

1. **Customer** - open by default. Pick a customer; this opens **Sales Order & Lines** automatically.
2. **Sales Order & Lines** - drop the sales order file (or **Choose file** / **Paste from clipboard**). Each attached file shows as its own thumbnail with an **Extract with AI from <filename>** action. Tap it to open the AI Extract dialog straight on that file's results table; remove any row you don't want with its own remove control before clicking **Confirm and prefill**, which appends the remaining rows as lines. **Add line** stays available for typing a row in by hand. The moment a first line lands, **Price** opens automatically.
3. **Price** - choose **List price** or **Selling price**. Choosing either opens **Additional Information**. Choosing **Selling price** also reveals a **Promotion** picker inside this same section, labelled optional - leave it blank if there's no promotion to link.
4. **Additional Information** - **Need by** and **Notes**, both optional; neither one blocks Submit.

A section you collapse stays collapsed - it only reopens automatically the first time its trigger condition is met, never again after that. You can open or close any section by hand at any time by tapping its header, and a collapsed section that already holds values shows a one-line summary (for example the customer's name, or "List price").

Click **Save Draft** or **Submit** as usual once you're done (see above).

### Viewing and editing a submitted price tag request

Once submitted, the request shows the same four sections read-only, all open, with the Sales Order thumbnails still tappable to preview.

* While the status is **New** or **Changes requested**, an **Edit** button shows in the header. Tapping it swaps every value for its input in place (same sections, same order) and the header shows **Save** / **Cancel** instead. Clicking **Save** writes your changes and returns to the read-only view **without** changing the status or restarting review.
* At **Designing** or **Design ready**, there is no Edit button - use **Request Changes** instead, as before.
* At **Approved** or **Ready**, nothing can be edited.
* Attachments can only be added or removed while the request is editable (New, Changes requested, or still a draft) - on any other status the Sales Order thumbnails are preview-only.

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
