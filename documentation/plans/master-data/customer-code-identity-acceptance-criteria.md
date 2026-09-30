# UAC - customer-code-identity (CUSTOMER-CODE-IDENTITY, re-scoped 30 Sep 2026)

The customer name a sales order was issued under is stored on the order and shown by the SO
screens; the customer master's name is the fallback. Plan: `PLAN-customer-code-identity.md`.

## Ingest

- **AC-01 [BE]** Given a customer `300-1001 / "1 LIVING DEPOT SDN BHD"` exists in the anchor
  company, when a sales order is pushed with `customer_code=300-1001` and
  `customer_name="MODERNMED SDN BHD"`, then the order links to that customer, the order's
  `debtor_name` is `"MODERNMED SDN BHD"`, and `customers.customer_name` is unchanged.
- **AC-02 [BE]** A re-push of the same order with another `customer_name` updates the order's
  `debtor_name` (trimmed); a push without one leaves the stored name alone; a dry run reports
  the change in `diff.debtor_name` and persists nothing.

## Screens (S1)

- **AC-03 [BE]** The SCM sales order serializer's `customer_name` (list and detail) is the
  order's `debtor_name` when set, else the master name; the list search matches it.
- **AC-04 [BE]** `customer_label.CUSTOMER_LABEL_SQL` (reorder demand popovers, order-qty
  ledger, container requests, trend drill) prints the order's `debtor_name` first, the master
  name for an order without one, the debtor code for an order nobody holds. The trend drill
  stays one row per customer key.
- **AC-05 [BE]** `order_service.so_outstanding_rows` (chatbot, MCP) prints the same order.

## Schema

- **AC-06 [BE]** Migration `sdn_0001_so_debtor_name` adds `sales_orders.debtor_name`
  (varchar 255, nullable) and leaves `uq_customers_company_code_name_lower` in place.

## Hand test

- **AC-07 [E2E]** On the crew test copy: an SO push with a changed debtor name shows that name
  on Supply Chain > Sales Orders (list and detail) while the Customers page still shows the
  master name; a re-push with another name updates the order.
