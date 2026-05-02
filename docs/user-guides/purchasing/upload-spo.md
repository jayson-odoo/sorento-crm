# Purchasing — Upload SPO (Supplier Purchase Order) allocations

Use this flow to bulk-import SPO allocations from an Excel file. SPO allocations link inbound shipments to products and warehouse destinations, and are what packing-list parsing produces automatically — but you can also upload them directly when needed.

## Steps

1. Open **Procurement → SPO Allocations** (URL: `/procurement-management/spo-allocations`). The page is titled **SPO Allocations**.
2. Click the **Import options** button in the toolbar (upload icon).
3. From the dropdown, click **Import SPO**.
4. The **SPO Import** dialog opens. Drop in or browse to your SPO Excel file.
5. Confirm to queue the import job (`spo_import`).

## What gets created

Each row becomes an **SPO allocation** linking:

- An **SPO number**.
- A **product** (`product_id`).
- A **warehouse** (`warehouse_id`).
- An **allocated quantity**.
- Optionally, an **inbound shipment** (`inbound_shipment_id`) — populated when the SPO row is linked to a packing list.

## How you'll see progress

The SPO Allocations page shows a **Latest SPO import** panel above the table once a job is running. It displays the job status and row counts in real time.

## How you'll be notified

- **Immediately:** in-app toast confirming the job was queued.
- **On completion:** the panel updates with the result. Email notifications fire if your tenant has them configured.

## SPO ↔ Purchase Request

The SPO allocation table does not store a direct foreign key to a purchase request. The typical end-to-end flow is:

1. **Purchase request** is approved (handled by project sales admin).
2. The supplier ships the goods, sending a **packing list** (Excel).
3. Purchasing uploads the packing list (see [Upload packing list](upload-packing-list.md)) — the integration creates the inbound shipment **and** the SPO allocations automatically.
4. SPO allocations link inbound shipment lines to the products and warehouses, and are visible on this page.

You only need to upload an SPO Excel directly when the packing-list flow doesn't apply (e.g. correcting historical data).

## See also

- [Upload packing list](upload-packing-list.md)
- [Upload product master](upload-product-master.md)
