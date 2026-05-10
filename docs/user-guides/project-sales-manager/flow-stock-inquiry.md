# Project Sales Manager — Flow a stock inquiry to purchasing (or reject)

Project sales reps submit stock inquiries through the [portal](../project-sales-rep/portal-overview.md). They land in the system as **Pending project sales** so you can review them before they reach the purchasing team. Your job is to either **approve** the inquiry — which sends it to purchasing — or **reject** it with a reason.

## Where to find inquiries waiting on you

Open **[Procurement → Stock Inquiries](/procurement-management/stock-inquiries)** (URL: `/procurement-management/stock-inquiries`). The page is titled **Stock Inquiries**.

Filter by **Status = Pending project sales** to see only the inquiries waiting on you. The full set of statuses is: **New**, **Pending project sales**, **Pending purchasing**, **Responded**, **Rejected**.

## Review


1. Click an inquiry row to open the detail page (URL: `/procurement-management/stock-inquiries/{id}`).
2. Read the header (requester, contact, products, requested quantities, notes) and check the **attachments**.
3. If you need clarification before deciding, open the actions menu (`⋯`) and click **Chat records** to message the rep on Respond.io.

## Approve (send to purchasing)

Click **Approve (send to purchasing)** in the toolbar. The inquiry moves to **Pending purchasing** and lands in the purchasing team's queue. They will respond with availability / lead-time / price (see [Purchasing — Review and respond to a stock inquiry](../purchasing/review-stock-inquiry.md)).

## Reject

If the request shouldn't go to purchasing (e.g. duplicate, out of scope, wrong customer), click **Reject** instead.


1. The **Reject stock inquiry** dialog opens.
2. Enter a **Rejection reason** — required (the dialog says: *"Enter a reason for the rejection. This is required."*). Placeholder: *"Reason for rejection..."*.
3. Click **Reject** to confirm. The inquiry moves to **Rejected** and the rep is notified.

## Reopen a rejected inquiry

If an inquiry was rejected by mistake, click **Reopen to pending project sales** on the rejected record. The **Reopen stock inquiry** dialog asks for an optional reason; click **Reopen** to confirm.

## How the rep is notified

* **On approve:** the rep receives a WhatsApp message through Respond.io confirming the inquiry was forwarded to purchasing.
* **On reject:** the rep receives a WhatsApp message with the rejection reason.

## See also

* [Approve a purchase request or sponsorship form via email](approve-via-email.md)
* [Purchasing — Review and respond to a stock inquiry](../purchasing/review-stock-inquiry.md)
* [Project Sales Rep — Submit a stock inquiry](../project-sales-rep/submit-via-portal.md)
