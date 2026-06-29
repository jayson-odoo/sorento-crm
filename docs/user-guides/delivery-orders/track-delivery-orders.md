# Delivery Orders — Track, view & edit

Use this flow to find a delivery order, read its full record (header, lines, financials, delivery & tracking), change its status, or create / edit one by hand. To bulk-import orders from Excel instead, see [Upload Delivery Orders](../warehouse/upload-delivery-orders.md).

## Where to go

Open **[Delivery Order Management → Delivery Orders](/order-management/orders)** (URL: `/order-management/orders`). The page is titled **Delivery Orders**.

## The list

Each row is one delivery order. Default sort is newest first (by created date), 50 per page.

Columns (left to right):

| Column | Meaning |
|----|----|
| **Delivery Order Number** | The order's unique number — the key you identify an order by. |
| **Debtor Name** | The customer / debtor the order belongs to. |
| **Delivery Order Date** | Date the order was placed. |
| **Estimated Delivery** | Estimated delivery date. |
| **Actual Delivery** | Date the order was actually delivered (blank until delivered). |
| **Delivery Days (2)** | Days taken to deliver; an amber warning icon shows when the KPI threshold is breached. |
| **Debtor Code** | The customer / debtor code. |
| **Agent** | Agent on the order. |
| **Cancelled** | **Yes** / **No**. |
| **Remarks CS** | Customer-service remarks. |
| **Type** | Delivery order type. |
| **Status** | Current delivery order status (coloured badge). |

### Search & filter

* **Search delivery orders…** — free-text box. Matches order number, debtor name, debtor code, transporter, and the linked customer's name / code.
* **Status** quick filter — **All statuses**, or pick any configured status.
* **Delivery order lines** quick filter — **All delivery orders** / **With delivery order lines** / **Without delivery order lines**.
* **Clear quick filters** — resets the two quick filters.
* **Filters** (toolbar) — advanced, field-by-field filter builder (the same engine used by **Export**).
* **Export** — download the current filtered set as `delivery_orders_export.xlsx`.
* **Columns** — show / hide / reorder columns (your choice is remembered per user).
* **Refresh** — reload the list.

Click any row to open its detail page.

## Detail page

The header shows the **Delivery Order Number** and its status badge, plus the debtor and delivery order date. Actions on the header:

* The **gear** button (tooltip *Change delivery order status*) — quick status switch (offers **New** / **Delivered** when those statuses exist, otherwise the full status list).
* **Edit** — open the edit form.
* **Delete** — hard-delete with a confirmation dialog (this action cannot be undone).
* Prev / next pager — walks the same filtered + sorted set you came from.

Three tabs:

1. **Delivery order information** — Delivery Order Number, Delivery Order Date, Debtor Code, Debtor Name, Agent, Delivery Order Type, Cancelled, Remarks CS, Delivery Order Status, Estimated Delivery Date, Actual Delivery Date, and Remarks. Below it sits the **Delivery Order Lines** card.
2. **Financial summary** — Subtotal Amount, Discount Amount, Tax Amount, Total Amount (formatted in MYR), plus Created / Last Updated timestamps.
3. **Delivery & tracking** — Debtor Code, Debtor Name, Agent, Delivery Order Type, Remarks CS, Customer (Ref), Cancelled, Delivery Time, Checker, Transporter, Driver Name, Lorry Plate, Warehouse, Salesman, Trips, Delivery Days (2), and delivery remarks.

### Delivery Order Lines

The **Delivery Order Lines** card lists the products on the order, with columns **Product**, **Warehouse**, **Qty**, **Unit price**, **Discount**, **Total**, **Tax**, **Total (excl)**, **Total (incl)**.

* **Add line** — opens **Add delivery order line**. Product ID and Warehouse ID are required (UUIDs from Products and Warehouses), plus Quantity.
* **Delete selected (n)** — bulk-delete the ticked lines.
* Empty state: *No delivery order lines. Import from Excel or add manually.*

Bulk-importing lines is usually faster — see [Upload Delivery Orders → Step 2](../warehouse/upload-delivery-orders.md#step-2--import-delivery-order-lines).

## Create / edit a single order

* **Create Delivery Order** (toolbar) → opens the create form. **Delivery Order Number**, **Delivery Order Date**, and **Delivery Order Status** are required; everything else is optional.
* **Edit** (detail header) → same form, pre-filled.

For more than a handful of orders, use the Excel import instead of typing each one — see the upload guide.

## Bulk delete

Tick rows in the list, then **Delete** in the bulk-action bar. The confirmation shows the count and warns the action cannot be undone.

## How you'll be notified

* In-app toast confirming create / update / delete.
* Import jobs are processed in the background — progress shows in the import status panels and the upload-activity drawer (see the upload guide).

## See also

* [Upload Delivery Orders](../warehouse/upload-delivery-orders.md) — bulk import tracking + lines.
* [Manage Customers](manage-customers.md)
* [Delivery Order Statuses](order-statuses.md)
* [Ask the assistant about delivery orders](data-analysis.md)
