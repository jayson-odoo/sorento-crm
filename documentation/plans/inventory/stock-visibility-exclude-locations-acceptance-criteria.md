# UAC: stock visibility "all except these" locations

Plan: `PLAN-stock-visibility-exclude-locations.md`.

- **AC-1 [BE]** Migration 508 (`down_revision = "507_pi_link_packing_row"`, re-parented
  onto main in fix round 1) adds `stock_visibility_policies.excluded_warehouse_ids`
  (ARRAY UUID, nullable) and CHECK `ck_stock_visibility_policies_one_location_rule`
  (`warehouse_ids IS NULL OR excluded_warehouse_ids IS NULL`). The existing migration test
  runs 416 then 508 and asserts a row with both lists non-null raises IntegrityError; the
  seeded default row reads `("detailed", None, None)`. Downgrade drops the column.
- **AC-2 [BE]** Detailed balance for a contact whose policy excludes warehouse A, with stock
  at A and B: only B's rows return. `warehouse_ids` on the row is NULL.
- **AC-3 [BE]** A warehouse C created (with stock) AFTER a policy excluding A was saved shows
  up in that contact's detailed balance without any change to the policy.
- **AC-4 [BE]** Two access types, one excluding {A} and one excluding {B}: the effective
  policy's `excluded_warehouse_ids == {A, B}` and neither warehouse's rows return.
- **AC-5 [BE]** Access type 1 includes {A, B}, access type 2 excludes {B}: only A's rows
  return (`warehouse_ids == {A, B}`, `excluded_warehouse_ids == {B}` on the merged policy).
- **AC-6 [BE]** A contact override excluding {A} beats an access-type row including {A, B}:
  B's rows and a third warehouse's rows return, A's do not.
- **AC-7 [BE]** Compact mode honours the exclusion (the excluded location's line and its
  quantity are absent from the summary; the total covers the rest). Availability mode judges
  the requested quantity against non-excluded stock only (enough at the excluded location
  alone = "no").
- **AC-8 [BE]** The detailed empty-path alternatives count only non-excluded stock (a
  neighbour product with stock solely at an excluded warehouse is not offered).
- **AC-9 [BE]** `PUT /contacts/{id}` with both `warehouse_ids` and `excluded_warehouse_ids`
  non-null returns 422 with detail `Pick locations to include or to exclude, not both.`; a
  body omitting `excluded_warehouse_ids` returns 422; a malformed excluded id returns 422,
  not 500.
- **AC-10 [BE]** `PUT` with `excluded_warehouse_ids: [A]` round-trips on all three tiers:
  the response's `override.excluded_warehouses` is `[{id, code, name}]` resolved by code, and
  `override.warehouses` is null. `GET` reads the same. The audit row records the change.
- **AC-11 [BE]** `StockVisibilityPolicyOut` declares `excluded_warehouses` (a
  `response_model` field-drop test, like the hide-zero one).
- **AC-12 [BE]** `excluded_warehouse_ids: []` is accepted and stored as `[]`; enforcement
  treats it as every active warehouse.
- **AC-13 [FE service]** `updateStockVisibilityPolicy` PUTs `excluded_warehouse_ids` exactly
  as given (null and a list); the policy type carries `excluded_warehouses`.
- **AC-14 [FE service]** The locations search calls the warehouses route with `limit=200`
  (still `is_active=true`, still server-searched).
- **AC-15 [FE card]** A stored exclusion renders the Exclude rule selected, the label
  "Excluded locations", and the excluded warehouses as `CODE - name` chips; no UUID in the DOM.
- **AC-16 [FE card]** Under Include with chips ticked, pressing Exclude keeps the same chips;
  Save sends `{warehouse_ids: null, excluded_warehouse_ids: [ids]}` with mode and
  hide_zero_locations.
- **AC-17 [FE card]** Under Exclude with no chips, the placeholder reads "All locations" and
  Save sends `excluded_warehouse_ids: []`, `warehouse_ids: null`.
- **AC-18 [FE card]** Exclude with no chips -> Include yields `warehouse_ids: null` (never
  `[]`); Exclude with chips -> Include carries the chips as the include list.
- **AC-19 [FE card]** "All locations" resets to Include + null and is disabled when the draft
  is already all (Include + null, or Exclude + []). "Dealer pool" sets Include + pool ids even
  when pressed under Exclude.
- **AC-20 [FE card]** Flipping the rule alone makes the card dirty (Save enabled); flipping
  back restores clean. An inherited exclusion from the access-type tier shows in the card
  with the "Access type: X" badge.
- **AC-21 [FE card]** The rule toggle offers exactly Include and Exclude, cannot be
  deselected, and is disabled while a save or removal is pending.
- **AC-22 [browser]** Via sidebar from `/`: User Management > Contacts > a contact > Stock
  visibility: open Locations, the "Select all N loaded" line reads N > 50 (77 on the 0907
  copy). Press Exclude, tick BRW-BB, Save, reload: Exclude selected, one chip BRW-BB. Press
  All locations, Save, reload: Include, "All locations". Usable at 375px and 1280px.
- **AC-23 [live]** With the contact excluding BRW-BB, `GET /api/v1/inventory/stock/balance`
  for that contact on a product stocked at BRW-BB and BRW returns the BRW row only.
