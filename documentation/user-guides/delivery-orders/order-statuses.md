# Delivery Order Statuses — Configure the status list

Use this flow to maintain the set of statuses a delivery order can move through (e.g. *New*, *Processing*, *Delivered*). These are the values that appear in the **Status** badge and the **Status** quick filter on the Delivery Orders list, and in the status-change gear menu on an order's detail page.

## Where to go

Open **[Delivery Order Management → Delivery Order Statuses](/order-management/order-statuses)** (URL: `/order-management/order-statuses`). The page is titled **Delivery Order Statuses**.

## The list

Each row is one status. Default sort is by **Sequence**, ascending.

| Column | Meaning |
|----|----|
| **Status Code** | Unique status identifier (alphanumeric, dashes, underscores only). |
| **Status Name** | The label shown on orders and in dropdowns. |
| **Sequence** | Display order — lower numbers appear first. |
| **Final Status** | **Yes** / **No** — whether this is a final / terminal status. |

### Search & filter

* **Search delivery order statuses…** — free-text box.
* **Filters → Final status** — **All** / **Final statuses** / **Non-final statuses** (applied within the list).

Click a row to open the status detail page.

## Create / edit a status

* **Create Delivery Order Status** (toolbar) → opens the form.
* Open a status and **Edit** → same form, pre-filled.

Fields:

| Field | Required | Notes |
|----|----|----|
| **Status Code** | Yes | Unique identifier (alphanumeric, dashes, underscores only). Not editable after creation. |
| **Status Name** | Yes | The display label. |
| **Description** | No | Free text. |
| **Sequence** | Yes | Position in the list — lower numbers appear first. |
| **Final Status** | — | Toggle to mark this status as a final / terminal status. |

Save with **Create Delivery Order Status** / **Update Delivery Order Status**.

## Delete

**Delete** uses a confirmation dialog. Take care deleting a status that orders are currently set to — removing an in-use status leaves those orders without a status badge until re-assigned.

## How you'll be notified

* In-app toast confirming create / update / delete.

## See also

* [Track Delivery Orders](track-delivery-orders.md)
* [Manage Customers](manage-customers.md)
* [Ask the assistant about order statuses](data-analysis.md)
