# UAC: estimated delivery date never in MCP / turn API output

- AC1. `not_found_error_message` for an order resolved under `order_status: delivered` with a
  display carrying `estimated_delivery_date` yields a message containing "hasn't been delivered
  yet" and "current status: <status>" and NOT containing the date string nor "estimated delivery".
- AC2. Every `customer_order` ResolvedEntity from `entity_resolver` (exact, prefix, AND-mode)
  has no `estimated_delivery_date` key in `display`; `actual_delivery_date` still present
  (trgm tier never carried it).
- AC3. MCP `crm_order_management_orders_list` and `_get` responses carry no
  `estimated_delivery_date` on any row (existing behaviour, pinned).
- AC4. CRM order list / detail API (`/api/v1/order-management/orders`) still returns
  `estimated_delivery_date` (UI unchanged).
