# Backend Requirements for Template Import Feature

## Required Dependencies

1. **Frontend**: Install xlsx library
   ```bash
   cd sorento_crm_frontend
   npm install xlsx
   ```

## Required Backend Endpoints

### 1. Bulk Import Orders
**Endpoint**: `POST /api/v1/order-management/orders/bulk-import`

**Request Body**:
```json
{
  "orders": [
    {
      "id": "optional-uuid", // If provided, update existing; if not, create new
      "order_number": "ORD-001",
      "order_date": "2024-01-01",
      "customer_id": "customer-uuid",
      "order_status_id": "status-uuid",
      "total_amount": 1000.00,
      // ... other order fields
    }
  ]
}
```

**Response**:
```json
{
  "created": 10,
  "updated": 5,
  "errors": []
}
```

**Logic**:
- For each order in the array:
 - If `id` is provided and exists: Update the order
 - If `id` is not provided or doesn't exist: Create a new order
- Return counts of created/updated records
- Return any errors encountered

### 2. Bulk Import Stock
**Endpoint**: `POST /api/v1/inventory/stock/bulk-import`

**Request Body**:
```json
{
  "stock": [
    {
      "id": "optional-uuid", // If provided, update existing; if not, create new
      "product_id": "product-uuid",
      "warehouse_id": "warehouse-uuid",
      "quantity": 100,
      "reserved_quantity": 10,
      // ... other stock fields
    }
  ]
}
```

**Response**:
```json
{
  "created": 10,
  "updated": 5,
  "errors": []
}
```

**Logic**:
- For each stock item in the array:
 - If `id` is provided and exists: Update the stock
 - If `id` is not provided or doesn't exist: Create a new stock record
- Return counts of created/updated records
- Return any errors encountered

### 3. Stock Balance Quantity Filter
**Endpoint**: `GET /api/v1/inventory/stock/balance`

**New Query Parameters**:
- `quantity_operator`: One of `gt`, `gte`, `lt`, `lte`, `eq`
- `quantity_value`: Numeric value to compare against

**Implementation**:
- Apply SQL WHERE clause based on operator:
 - `gt`: `quantity > quantity_value`
 - `gte`: `quantity >= quantity_value`
 - `lt`: `quantity < quantity_value`
 - `lte`: `quantity <= quantity_value`
 - `eq`: `quantity = quantity_value`
