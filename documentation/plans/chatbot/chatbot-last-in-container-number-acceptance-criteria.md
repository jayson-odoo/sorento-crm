# UAC: "last in" answer carries the container number

Plan: `PLAN-chatbot-last-in-container-number.md`. Extends AC-9 of
`chatbot-warehouse-entity-and-last-in-acceptance-criteria.md`.

- AC-1 Service, per-product branch. A product with one visible line whose
  `spo_allocations.container_number = "CMAU7650091"`: `last_receipt_rows(db,
  product_ids=[P])[0]["container_number"] == "CMAU7650091"`.
- AC-2 Service, unscoped branch. The same line answers `container_number ==
  "CMAU7650091"` through `last_receipt_rows(db, top_n=1)` (no `product_ids`).
- AC-3 Absence. A line with `container_number` NULL answers `row["container_number"] is
  None`; the key is present, the value None (the presenter drops it).
- AC-4 Route. `GET /api/v1/procurement/spo-allocations/last-receipt?product_ids=P` returns
  `data[0].container_number == "CMAU7650091"` for the AC-1 line.
- AC-5 Presenter order. For a row carrying every field, `_spo_last_receipt` renders
  EXACTLY, in this order: `SPO Number`, `Container Number`, `Product Code`,
  `SPO Quantity`, `GR Quantity`, `SPO Date`, `GR Date`, `Warehouse`. Asserted as an exact
  list. `Container Number` is at index 1, directly under `SPO Number`, with key
  `container_number`.
- AC-6 Presenter absence. A row with `container_number` None (or missing) renders the
  previous seven labels in their previous order; nothing renders as "Container Number:"
  with an empty value.
- AC-7 Catalog. The `crm_procurement_spo_allocations_last_receipt_list` description names
  `container_number` right after `spo_number` in its "Each row reads in this order" list
  and says it is present only when the line was ingested from a shipping order that named
  its container.
- AC-8 Live. Lane backend + MCP up; the MCP tool called for a product on
  `SPO-2026/09-0030` (0907 copy) renders `Container Number: CMAU7650091` under
  `SPO Number: SPO-2026/09-0030`; called for a product whose last line predates D6, no
  `Container Number` field appears.
