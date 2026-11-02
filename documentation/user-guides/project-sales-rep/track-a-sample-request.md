# Project Sales Rep - Track a sample request: the delivery date and the delivery

After you submit a sample request, it goes through two stages:

| Stage | Statuses | What happens |
| --- | --- | --- |
| **Processing** | Submitted, Processing, Customer confirmed | The sample team takes the request and answers your **Request Delivery Date** |
| **Delivery** | Delivered | The goods went out on an AutoCount consignment |

Draft and Cancelled are not in either stage.

## The sample team's answer to your delivery date

When the sample team starts processing your request, it must say whether it can meet the date you asked for.
Open the request: under **Request Delivery Date**, **Sample team** reads one of these:

* **Can meet the requested date**
* **Proposes 9 Dec 2026**, with a **New date** badge, plus the team's note when it wrote one
* **Not answered yet**, before the team starts processing

You do not have to accept a new date. If it does not work for your customer, tell the sample
team. Once processing has started, only the team can cancel the request.

The team can change its answer while the request is Processing or Customer confirmed. The page
always shows the latest answer.

In the **Sample Requests** list and on the project's **Samples Request** tab, the **Delivery**
column shows the team's proposed date with a **New date** badge, or your requested date when the team can meet it.
Sorting by **Delivery** uses the date shown.

## Delivered

The request becomes **Delivered** when the sample team links the AutoCount consignment
(`CG-...`) that carried the goods. Nobody marks it by hand. The page shows:

* **Consignment No**: the consignment number and its date
* **Delivered**: the date, then where it came from:
  * **(Order Tracking)**: the delivery date the order tracking upload recorded for that
    consignment
  * **(consignment date)**: the consignment's own date, used when order tracking has no delivery yet.
    When the tracking date arrives later, the request updates to it on its own, and so does
    **Return due**.

If the consignment is voided in AutoCount, the request goes back to Customer confirmed, or to Processing
if the customer never confirmed. The page then shows **Voided in AutoCount** next to the
consignment number.

## Filters

**Filters > Stage** narrows the list to **Processing**, **Delivery**, or both. A stage filter
also shows Delivered requests, which the list otherwise hides by default.

## See also

* [Start a sample request from the project's quotation](sample-request-from-quotation.md)
* [Process a sample request (sample team)](../project-sales-admin/process-a-sample-request.md)
