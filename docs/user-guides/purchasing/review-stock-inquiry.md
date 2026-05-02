# Purchasing — Review and respond to a stock inquiry

When a project salesperson submits a stock inquiry that needs purchasing's input, the inquiry moves to the **Pending purchasing** state. Purchasing reviews the request, replies with availability/lead-time/price, or rejects it with a reason.

## Where to find pending inquiries

Open **Procurement → Stock Inquiries** (URL: `/procurement-management/stock-inquiries`).

Filter the list by **Status = Pending purchasing** to see only inquiries waiting on your team. The other statuses you'll encounter are: *New*, *Pending project sales*, *Responded*, and *Rejected*.

## Reply to an inquiry

1. Click an inquiry row to open the detail page (URL: `/procurement-management/stock-inquiries/{id}`).
2. Review the inquiry header (requester, contact, products, requested quantities, notes) and any attached files.
3. Click **Edit purchasing response** in the toolbar.
4. Fill in the response in the dialog (titled **Edit purchasing response**) — typical fields are availability, price, lead time, and remarks per line.
5. Choose how to finish:
   - **Update & Reply** — saves your response **and** sends it back to the requester. Use this when your reply is complete and ready to share.
   - **Save only** — saves your draft response without notifying the requester. Use this for work-in-progress edits.

After **Update & Reply** the inquiry moves to **Responded** and the requester is notified.

## Reject an inquiry

If the request can't be fulfilled, click **Reject** on the detail page.

1. The **Reject stock inquiry** dialog opens.
2. Enter a **Rejection reason** — this field is **required** (the dialog says: *"Enter a reason for the rejection. This is required."*).
3. Confirm. The inquiry moves to **Rejected** and the rejection reason is stored on the record and sent to the requester.

## Chat directly with the requester

If you need clarification before responding, use the chat panel:

1. From the inquiry detail page, click **Chat records** (message-square icon) in the toolbar.
2. A side panel opens with the conversation history for this inquiry.
3. Send messages directly to the contact — replies show up in the same panel as the requester replies.

This panel is wired to the same conversation that the requester uses on the portal, so messages flow both ways.

## How the requester is notified

- **On Update & Reply:** the requester receives the response on their portal conversation and (depending on tenant configuration) by their preferred channel (e.g. WhatsApp).
- **On Reject:** the requester is notified with the rejection reason.
- **Chat messages** are pushed to the contact's conversation in real time.

## See also

- [Shared upload flow](../_shared/upload-flow.md) (for attaching files to your response)
