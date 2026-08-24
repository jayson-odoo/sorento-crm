# 1.5-Purchasing - Review and respond to a stock inquiry

When a project sales manager flows a stock inquiry to purchasing, the inquiry moves to the **Pending purchasing** state. Purchasing reviews the request, replies with availability / lead-time / price, or rejects it with a reason.

## Where to find pending inquiries

Open **[Procurement → Stock Inquiries](/procurement-management/stock-inquiries)** (URL: `/procurement-management/stock-inquiries`).

Filter the list by **Status = Pending purchasing** to see only inquiries waiting on your team. The full set of statuses is: **New**, **Pending project sales**, **Pending purchasing**, **Responded**, **Rejected**.

## Reply to an inquiry


1. Click an inquiry row to open the detail page (URL: `/procurement-management/stock-inquiries/{id}`).
2. Review the inquiry header (requester, contact, products, requested quantities, notes) and any attached files.
3. Click **[Edit purchasing response](#guide_target=procurement.stock-inquiries.edit-purchasing-response-button)** in the toolbar.
4. Fill in your response in the **Edit purchasing response** dialog. The dialog tells you: *"Save updates the record only. Update & Reply saves your text and sends it to the contact."*
5. Choose how to finish:
   * **[Save only](#guide_target=procurement.stock-inquiries.save-response-button)** - saves your draft response without notifying the requester. Use this for work-in-progress edits.
   * **[Update & Reply](#guide_target=procurement.stock-inquiries.update-and-reply-button)** - saves your response **and** sends it back to the requester via Respond.io. Use this when the reply is complete.

After **Update & Reply** the inquiry moves to **Responded** and the requester is notified.

## Reject an inquiry

If the request can't be fulfilled, click **[Reject](#guide_target=procurement.stock-inquiries.reject-button)** on the detail page.


1. The **Reject stock inquiry** dialog opens.
2. Enter a **Rejection reason** - this field is required (the dialog says: *"Enter a reason for the rejection. This is required."*). Placeholder: *"Reason for rejection..."*.
3. Click **[Reject](#guide_target=procurement.stock-inquiries.reject-confirm-button)** to confirm. The inquiry moves to **Rejected** and the rejection reason is stored on the record and sent to the requester.

## Reopen a rejected inquiry

If a rejection was issued in error, click **[Reopen to pending purchasing](#guide_target=procurement.stock-inquiries.reopen-button).** The **Reopen stock inquiry** dialog asks for an optional reason; click **[Reopen](#guide_target=procurement.stock-inquiries.reopen-confirm-button)** to confirm.

## Chat directly with the requester

If you need clarification before responding, use the chat panel:


1. From the inquiry detail page, open the actions menu (`⋯`) and click **Chat records**.
2. A side panel opens with the conversation history for this inquiry.
3. Send messages directly to the contact - replies show up in the same panel as the requester's replies.

You can also use **Update & Reply** from the same actions menu to compose a reply prefilled with the saved purchasing response.

## How the requester is notified

* **On Update & Reply:** the requester receives the response on their portal conversation and via WhatsApp through Respond.io.
* **On Reject:** the requester is notified with the rejection reason.
* **Chat messages** are pushed to the contact's conversation in real time.

## See also

* [Shared upload flow](../_shared/upload-flow.md) (for attaching files to your response)
* [Project Sales Manager - Flow stock inquiry to purchasing](../project-sales-manager/flow-stock-inquiry.md)
