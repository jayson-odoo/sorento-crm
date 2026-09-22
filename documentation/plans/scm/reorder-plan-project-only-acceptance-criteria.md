# UAC: A Project plan buys for the order inquiries alone (22 Sep 2026)

Plan: `PLAN-reorder-plan-project-only.md`. AC-PO-n.

- AC-PO-1: A Project run (demand_class = project) does not admit a product whose only reason
  to be planned is being below its reorder level; the product emits no recommendation.
- AC-PO-2: A Dealer run still admits and buys for that same product (unchanged).
- AC-PO-3: In a Project run, a product with an acknowledged, unlinked ORDER row of qty 20 and
  a dealer stock position below its reorder level emits exactly one recommendation whose
  recommended quantity is 20 and whose reason label starts with "project buy".
- AC-PO-4: In a Dealer run that same product's recommendation is the retail top-up (today's
  figure), not 20.
- AC-PO-5: A Project run scoped to `so_numbers` emits nothing for a product whose only ORDER
  row sits on an order outside the list.
- AC-PO-6: A Project run emits nothing for a product whose ORDER row is fully linked.
- AC-PO-7: MOQ and order multiples still round a Project run's project need (need 20, MOQ 50
  -> 50).
- AC-PO-8: In a pooled product, sibling on-hand does not reduce a Project run's firm project
  Buy (need 10 at A, 100 on hand at B -> Buy 10).
- AC-PO-9: The run header's Recommendations / Buy / Cash counts equal the sum of the lines
  emitted under AC-PO-1..8 (no phantom counts from the dropped leg).
- AC-PO-10: `test_pool_netting_parity.py`, `test_reorder_run_product_scope.py`,
  `test_reorder_run_scope_isolation.py`, `test_reorder_plan_demand_scope.py` unchanged and
  green.
- AC-PO-11 (browser, once a slot frees): Start Plan, Demand = Project, the owner's 14 orders,
  01/09 to 16/11: the plan lists only inquiry-backed lines (45 on the 21 Sep copy), no
  MPW800 / SRTBT1863-15 style reorder-level lines.
