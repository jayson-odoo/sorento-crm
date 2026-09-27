# UAC: S1 achievement query performance (#1319)

- AC1 Saving an all-products target on the Targets screen returns in under a second on a
  production-like volume of sales order lines.
- AC2 The portal and Targets screens show the same achieved figures as before the change.
- AC3 A save runs the achievement calculation at most once.
- AC4 The achievement statement compares `sales_order_lines.company_id` without a cast and
  never reads a sales order line dated outside every period being counted.
