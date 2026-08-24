# Inventory - Stock batches and expiry

A stock batch (lot) tracks a quantity of one product, received into one warehouse, with optional manufactured and expiry dates and a lifecycle status. Use this page to watch what's expiring and to see batch-level availability.

## Where

Open [**Inventory Management → Stock Batches**](/inventory-management/stock-batches). The page is titled **Stock Batches**.

Requires the `inventory.stock_batches.view` permission to open.

## The list

| Column | What it shows |
|--------|----------------|
| **Product Code** | The product the batch belongs to. |
| **Batch Code** | The batch / lot identifier (globally unique). |
| **Quantity** | Items currently in the batch. |
| **Manufactured Date** | When the batch was produced (may be blank). |
| **Expiry Date** | Use-by date (may be blank). A red **Expires in {days} days** badge appears when the batch expires within the next 30 days. |
| **Warehouse** | Where the batch is held. |
| **Status** | Lifecycle status badge - see below. A batch with no status shows ** - **. |

### Status values

| Status | Meaning |
|--------|----------|
| **Available** | In stock and usable. |
| **Reserved** | Allocated to an order. |
| **Damaged** | Contains damaged items. |
| **Expired** | Past its expiry date. |
| **Returned** | Returned into the warehouse. |

## Filtering and searching

* **Search batches...** - searches the list.
* **Status** - a dropdown: **All statuses**, **Available**, **Reserved**, **Damaged**, **Expired**, **Returned**.
* **Clear filters** - appears when the status filter is active.

## Toolbar

* **Create Batch** - opens the new-batch screen.
* **Export** - downloads the batches as `stock_batches_export.xlsx`.
* A **Refresh** control reloads the list.

> Note: at the time of writing, **Create Batch** navigates to a new-batch screen that is not yet implemented in the UI - batches today are created by the backend / import pipeline rather than hand-entered. Confirm with your integrations admin before relying on manual batch creation.

## Watching expiry

The fastest expiry check is the **Expiry Date** column: any batch due within 30 days is flagged with the red **Expires in {days} days** badge. The AI assistant can also answer expiry questions directly - see [Inventory - Data analysis for the AI assistant](data-analysis.md).

## What's captured

Per batch: `product_id`, `warehouse_id`, `batch_code`, `quantity`, `manufactured_date`, `expiry_date`, `received_date`, `status`, `created_at`.

## See also

* [Inventory - Understand stock levels](understand-stock-levels.md)
* [Inventory - Read the stock ledger](read-the-stock-ledger.md)
