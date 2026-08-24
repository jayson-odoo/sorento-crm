# 1.3-Warehouse - Upload Delivery Orders (order tracking + lines)

Use this flow to bulk-import delivery orders and their line items. The flow has two imports: the **tracking** import (one row per order: dates, customer, totals) and the **delivery order lines** import (one row per product line on each order).

## Where to upload

Open **[Delivery Order Management → Delivery Orders](/order-management/orders)** (URL: `/order-management/orders`). The page is titled **Delivery Orders**.

Toolbar:

* **[Import](/order-management/orders#guide_target=order-management.delivery-orders.import-button)** - dropdown with **Import tracking** and **Import delivery order lines**.
* **Create Delivery Order** - manual single-record creation.
* **Quick filters** / **Filters** / **Export** / **Columns** / **Refresh** - DataGrid tools.

## Step 1 - Import tracking (order header)


1. Click **[Import](/order-management/orders#guide_target=order-management.delivery-orders.import-button)** → **Import tracking**.
2. Drag in or browse to your tracking Excel file.
3. (Recommended) Click **[Test](/order-management/orders#guide_target=template-upload.test-button)** to validate first; resolve errors before uploading.
4. Click **[Upload](/order-management/orders#guide_target=template-upload.confirm-button)**. The job is queued (`order_tracking_import`).

### Tracking columns

| Column | Required | Notes |
|----|----|----|
| **Order Number** | Yes | Used as the unique key for upserts (or use the optional **ID** column to update by UUID). |
| **Order Date** | Optional | Date the order was placed. |
| **Estimated Delivery Date** / **Promised Delivery Date** | Optional | The delivery promise. |
| **Actual Delivery Date** | Optional | Filled in once the order is delivered. |
| **Customer ID** | Optional | UUID of the customer record. |
| **Order Status ID** | Optional | UUID of the lookup-set option. |
| **Subtotal Amount** | Optional | Decimal. |
| **Discount Amount** | Optional | Decimal. |
| **Tax Amount** | Optional | Decimal. |
| **Total Amount** | Optional | Decimal. |
| **Remarks** | Optional | Free text. |
| **Billing Address ID** / **Shipping Address ID** | Optional | UUID references to address records. |
| **ID** | Optional | UUID. If present, the row updates an existing order; if missing, a new order is created. |

Accepted date formats: ISO, `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`. Numeric fields tolerate currency symbols (`RM`, `$`), commas, and spaces.

## Step 2 - Import delivery order lines

After the tracking import finishes:


1. Click **[Import](/order-management/orders#guide_target=order-management.delivery-orders.import-button)** → **Import delivery order lines**.
2. Drag in or browse to your lines Excel.
3. (Recommended) Click **[Test](/order-management/orders#guide_target=template-upload.test-button)** to validate.
4. Click **[Upload](/order-management/orders#guide_target=template-upload.confirm-button)**. The job is queued (`delivery_order_detail_import`).

### Delivery order line columns

| Column (any of these is accepted) | Required | Notes |
|----|----|----|
| **Doc No** / **Doc Number** / **Order Number** | Yes | Must match an existing order header. |
| **Item Code** / **Product Code** | Yes | Looked up against the product master. |
| **Location** / **Warehouse** / **Warehouse Code** | Yes | Looked up against the warehouse master. |
| **Qty** / **Quantity** | Yes | Integer, must be greater than `0`. |
| **Unit Price** | Optional | Decimal. |
| **Discount** | Optional | Decimal / percentage. |
| **Total** | Optional | Decimal. |
| **Tax** | Optional | Decimal. |
| **Total Excluding Tax** | Optional | Decimal. |
| **Total Including Tax** | Optional | Decimal. |

Duplicate lines on the same order with the same product + warehouse combination are kept as **separate sequenced lines** - they are not aggregated.

## How you'll see progress

The **Delivery Orders** page shows two status panels above the table:

* **Latest tracking import** - for `order_tracking_import`.
* **Latest delivery order lines import** - for `delivery_order_detail_import`.

Each panel updates with `queued` → `running` → `finished` (or `failed`) and row counts.

## How you'll be notified

* **Immediately:** in-app message at the bottom right confirming the job was queued.
* **On completion:** the system notifies you via email notification & in-app notification (in which you can access from the bell icon at the top right).

## See also

* [Upload GRN](upload-grn.md)
