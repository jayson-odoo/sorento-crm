# Delivery Order Management - Asking the AI assistant for data

This guide is for **the AI assistant** (and for users who want to know what it can answer). It maps natural-language questions about **delivery orders, order statuses, and customers** to the data the assistant can read, the filters it should use, and the date columns it must pick between.

The assistant reads delivery-order data through three tools, all backed by the orders table:

| Tool | Use it for |
|----|----|
| `crm_order_management_orders_list` | List / filter / sort delivery orders. The default tool for "list orders …". |
| `crm_order_management_orders_by_product_list` | Distinct **customer sales** orders that contain a specific product. Requires a `product_ids` narrower. |
| `crm_master_customers_list` | "Who are our customers?" / "top customers" - distinct customers aggregated from orders, each with an order count. |

> **Result caps.** External / AI callers are hard-capped at **20 rows per page** on these tools. For larger sets, narrow with UUID + date filters and walk pages with `page`.

> **No UUIDs in answers.** Order rows carry no UUIDs - identify an order by its **order number**, a customer by **debtor name / code**, a status by its **name**.

---

## The single most important rule: which DATE column?

Delivery orders have two date dimensions. Picking the wrong one silently returns the wrong set.

| Date column | Means | Use when the user says… |
|----|----|----|
| **`actual_delivery_date`** (`actual_delivery_date_from` / `_to`) | When the order was actually **delivered** (blank until delivered). **This is the default.** | "delivered", "received", "arrived", "for delivery", "pending delivery", "delivery date" - **and any bare time window** ("today", "this week", "February 2026", "last month") and general "orders in [period]" questions. |
| **`order_date`** (`order_date_from` / `_to`) | When the order was **placed**. | Only when the user **explicitly** names the placement date: "placed", "created", "raised", "opened", "booked", or literally "order date". |

When in doubt, use `actual_delivery_date`.

Both accept flexible formats: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY/MM/DD`, ISO datetimes, and month forms `YYYY-MM`, `MM/YYYY`, or `Month YYYY`. Ranges are inclusive.

---

## Entity 1 - Delivery Order

**Tool:** `crm_order_management_orders_list` (`GET /api/v1/order-management/orders`)

### Fields on each row
Order number, order date, estimated delivery date, actual delivery date, delivery days, debtor name, debtor code, agent, cancelled flag, order type, remarks (CS), `pickup_time`, checker, transporter, driver name, lorry plate, warehouse, salesman, trips, subtotal / discount / tax / total amount, and `order_status` (a **plain string**, the status name).

### Filters
| Filter | Notes |
|----|----|
| `query` | Free text - matches order number, debtor name, debtor code, transporter, and the linked customer name / code. |
| `customer_ids` | Canonical customer UUIDs (csv / JSON / repeated). Matches the order's customer, with a debtor-name fallback for legacy rows. Resolve a customer name to its UUID first. |
| `product_ids` | Orders that contain any of these products. |
| `transporter_ids` | Canonical transporter UUIDs (text fallback for legacy rows). |
| `customer_id` / `order_status_id` | Single-value UUID equality filters. Use `order_status_id` to filter by a status (resolve the status name to its UUID). |
| `has_order_lines` | `yes` = at least one line, `no` = no lines, omit = all. |
| `has_actual_delivery_date` | `yes` = delivered, `no` = not yet delivered, omit = all. |
| `order_date_from` / `order_date_to` | Placement-date window (see the date rule above). |
| `actual_delivery_date_from` / `actual_delivery_date_to` | Delivery-date window - **default** for bare time windows. |
| `sort` / `dir` | See sortable fields below. `dir` is `asc` / `desc`. |

### Sortable fields
`order_number`, `order_date`, `estimated_delivery_date`, `actual_delivery_date`, `delivery_days`, `debtor_name`, `debtor_code`, `agent`, `is_cancelled`, `remarks_cs`, `order_type`, `total_amount`, `created_at`, `updated_at`, and `order_status.status_name`.

### Example questions

1. **"List orders for customer Deluxe Home Center delivered between 1 Jan 2026 and 31 Mar 2026."**
   Resolve "Deluxe Home Center" → `customer_ids`; `actual_delivery_date_from=2026-01-01`, `actual_delivery_date_to=2026-03-31`. (Falls back to debtor-name match for legacy rows.)

2. **"Show undelivered orders older than 30 days."**
   `has_actual_delivery_date=no` + `order_date_to=<today − 30 days>` (placed over 30 days ago and still not delivered). Sort `order_date asc` to surface the oldest first.

3. **"Orders delivered this month."**
   `actual_delivery_date_from=<first of month>`, `actual_delivery_date_to=<last of month>` (bare window → delivery date). To group by status, read each row's `order_status` string and tally.

4. **"List delivery orders for debtor code 300-D093."**
   Pass the code as `query` (or resolve to `customer_ids`). Returns that debtor's orders.

5. **"Which orders are still pending delivery?"**
   `has_actual_delivery_date=no`. Add `order_date_from` / `_to` to scope to a placement window if asked.

6. **"Orders placed in February 2026"** vs **"orders delivered in February 2026."**
   *Placed* → `order_date_from=2026-02`, `order_date_to=2026-02`. *Delivered* → `actual_delivery_date_from/to=2026-02`. Choose by the verb.

7. **"Show the 20 most recent delivered orders."**
   `has_actual_delivery_date=yes`, `sort=actual_delivery_date`, `dir=desc`, `limit=20`.

8. **"List cancelled orders this quarter."**
   Quarter window on `actual_delivery_date_*` (or `order_date_*` if they say "placed"); read the `cancelled` flag and report only cancelled rows. (There is no server-side `is_cancelled` filter param - filter the returned rows, paginating if needed.)

9. **"Orders with no delivery order lines."**
   `has_order_lines=no`.

---

## Entity 2 - Orders containing a product

**Tool:** `crm_order_management_orders_by_product_list` (`GET /api/v1/order-management/orders/by-product`)

Distinct **customer sales** orders (outgoing / sold - **not** incoming stock) that contain a given product. A `product_ids` narrower is **required**; without it the tool returns an empty page.

Optional: `customer_ids`, `transporter_ids`, and the `actual_delivery_date_from` / `_to` window. Sort / page as usual.

### Example questions

10. **"List orders containing product <X> delivered last week."**
    Resolve product → `product_ids`; `actual_delivery_date_from/to` = last week's range.

11. **"Which customers bought product <X> this year?"**
    `product_ids` + `actual_delivery_date_from=<Jan 1>`; read the debtor names off the returned orders.

> For "is product X **incoming** / arriving / pending stock?" use the incoming-stock tool instead - `by-product` here is outgoing sales only.

---

## Entity 3 - Customer (debtor aggregation)

**Tool:** `crm_master_customers_list` (`GET /api/v1/order-management/orders/debtors`)

Distinct customers **aggregated from the orders table** by debtor name, each row returning `debtor_name`, `debtor_code`, and `order_count`. This is the source of truth for "who are our customers" - real customer identity in the business lives on the orders' debtor name / code, not the separate Customers master screen (which the assistant cannot read directly).

| Filter / option | Notes |
|----|----|
| `customer_ids` | Canonical customer UUIDs - narrows the source orders before aggregation. |
| `sort` | `debtor_name`, `debtor_code`, or `order_count`. |
| `dir` | `asc` / `desc`. |
| `page` / `limit` | External callers hard-capped at 20. |

### Example questions

12. **"Top 10 customers by order count."**
    `sort=order_count`, `dir=desc`, `limit=10`.

13. **"How many orders does each customer have?"**
    Default listing - each row carries `order_count`. Page through for the full set.

14. **"List our customers alphabetically."**
    `sort=debtor_name`, `dir=asc`.

15. **"How many orders does <customer> have?"**
    Resolve to `customer_ids` (or read the matching `debtor_name` row) and report its `order_count`.

---

## Entity 4 - Order Status

There is no dedicated status-listing tool for the assistant. Statuses surface two ways:

* On each order row as the `order_status` **string** (the status name) - so you can group / count orders by status from `crm_order_management_orders_list` results.
* As a filter: resolve a status **name** to its UUID and pass it as `order_status_id` to list only orders in that status.

### Example questions

16. **"How many orders are in each status this month?"**
    List orders for the month (delivery-date window) and tally the `order_status` string across pages.

17. **"List orders that are 'Delivered'."**
    Resolve "Delivered" → `order_status_id` and filter, or read the `order_status` string off the rows.

---

## Things to remember

* Default to **`actual_delivery_date`** for bare time windows; only use `order_date` when the user explicitly names the placement date.
* Identify orders by **order number**, customers by **debtor name / code**, statuses by **name** - never by UUID in the answer.
* Results are capped at **20 rows** per call for AI callers - narrow and paginate rather than asking for everything.
* `crm_order_management_orders_by_product_list` is **outgoing sales** and **requires** `product_ids`; for incoming stock use the incoming-stock tool.

## See also

* [Track Delivery Orders](track-delivery-orders.md)
* [Manage Customers](manage-customers.md)
* [Delivery Order Statuses](order-statuses.md)
* [Upload Delivery Orders](../warehouse/upload-delivery-orders.md)
