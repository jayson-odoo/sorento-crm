# PLAN: stock reply Total O/S respects warehouse visibility (STOCK-TOTAL-OS-SCOPE)

Status: in progress (small fix track: no migration, no RBAC change, no new ingest surface)

Owner decision 2 Oct 2026, option (a).

## Problem

The chatbot stock reply's Total line prints `(O/S: n)` from `open_so_qty_by_product`
(`app/services/inventory_service.py`), which sums every open SO line of the product with no
warehouse filter. A contact whose policy hides a warehouse is therefore told that warehouse's open
demand inside the Total (prod: MWC7624-RL-S10 `Total 54 (O/S: 531)`, `BRW 0 (O/S 0)`,
`MWH 54 (O/S 0)`).

## Rule

- Total O/S = sum of open SO qty on warehouses the contact may see: the same
  `warehouse_criterion(policy, ...)` and active-warehouse filter the location lines use.
- Open SO lines with no warehouse print on their own line, `Unassigned O/S: N`, only when N > 0,
  and are not added to Total O/S.
- Open SO on a hidden warehouse is never shown or hinted.
- No `contact_id` (staff grid, no policy): unchanged; the summary keeps the product total.
- Open-SO aggregates AND the company predicate in by hand (column-only aggregate).

## UAC

1. Policy includes only W1; open SO 10 on W1, 7 on hidden W2, 3 with no warehouse:
   Total O/S 10, Unassigned O/S 3, nothing reads 7 or 20.
2. No unassigned lines: no `Unassigned O/S` line.
3. Staff call (no contact): Total O/S unchanged (all lines).
4. Open SO of another company is not counted when the request is company scoped.
