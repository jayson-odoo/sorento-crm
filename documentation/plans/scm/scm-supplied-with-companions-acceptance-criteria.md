# UAC: "supplied with" companions on the Order Inquiry

Plan: `PLAN-scm-supplied-with-companions.md`. Status: rulings in 9 Sep 2026, ready for Phase 1.

Fixture (CI has no data, seed it): company C, supplier S1 and S2, products
CKS1050 (host), CKSW015 (companion), X, Y (pair hosts), SC (pair companion).
Rules: CKSW015 with CKS1050 ratio 1 supplier NULL; SC with X + Y ratio 1
supplier S1.

## A. Configuration

| id | given | when | then |
| --- | --- | --- | --- |
| A1 | companion product page, Suppliers tab | open | "Supplied with" section lists its rules: hosts, supplier or "Any", ratio |
| A2 | Add | hosts picked via shared product search (multi), supplier clearable, ratio default 1, fractional accepted (0.5) | rule saved; list shows it without reload |
| A3 | rule exists | Delete | `ConfirmDeleteDialog`, then hard delete |
| A4 | same companion, same supplier | Add again | 409, message names the existing rule |
| A5 | host product page | open | read-only "Ships with" list naming each companion and ratio |
| A6 | product named as host or companion | delete product | refused (RESTRICT), message names the rule |
| A7 | company D user | GET rules | sees none of company C's rules |

## B. Derivation on the row

Each case: one SO, fulfilment board confirms Buy for the quantities named,
`refresh_for_decision` raises the rows, then assert `bundled_qty`,
`bundled_with_row_id`, demand and state.

| id | rows raised | expect |
| --- | --- | --- |
| B1 | CKS1050 1, CKSW015 1 | CKSW015 bundled 1, anchor = CKS1050 row, state `placed`, demand 0 |
| B2 | CKSW015 1 alone | bundled 0, `raised`, demand 1 (ala carte) |
| B3 | CKS1050 1, CKSW015 3 | bundled 1, `partly_linked`, demand 2 |
| B4 | CKS1050 2, CKSW015 1 | bundled 1, demand 0 |
| B5 | X 2, Y 2, SC 2 (host linked to S1 PO) | SC bundled 2, demand 0 |
| B6 | X 3, Y 2, SC 3 | SC bundled 2, demand 1 |
| B7 | X 2, SC 2 (no Y row) | bundled 0, demand 2 |
| B8 | X 2, Y 2, SC 2, hosts linked to S2 PO | bundled 0 (supplier mismatch) |
| B9 | X 2, Y 2, SC 2, hosts unlinked, X primary supplier S1 | bundled 2 |
| B10 | B1 then CKS1050 row cancelled by a revision | CKSW015 bundled 0, `raised`, demand 1 |
| B11 | SC row already holds a manual SPO link of 1, X 2 Y 2 SC 2 | link kept, bundled 1, `placed` |
| B12 | rule inactive | bundled 0 |
| B15 | rule ratio 0.5, CKS1050 4, CKSW015 3 | bundled 2, demand 1 |
| B13 | CKS1050 covered from stock (no row), CKSW015 Buy 1 | bundled 0, demand 1 |
| B14 | `derive_bundles` run twice | identical result, no duplicate anchors |

## C. Cascade and planner

| id | given | then |
| --- | --- | --- |
| C1 | B1 | `auto_place_for_products` skips CKSW015 (need 0); no link created |
| C2 | B3 | cascade need for CKSW015 is 2 |
| C3 | B1, reorder run | no buy recommendation for CKSW015 |
| C4 | B2, reorder run | buy recommendation for CKSW015 qty 1 |

## D. Worklist

| id | given | then |
| --- | --- | --- |
| D1 | B1, host on a PO | cell `Included with CKS1050 · 1 of 1`; info icon opens the host lightbox |
| D2 | B1, host not found | cell `Included with CKS1050 · Not found (new order)` |
| D3 | B3 | cell `1 with CKS1050 · 0 of 2`; lightbox lists the anchor and the row's own documents |
| D4 | B1, host on PO | tiles: Use PO includes CKSW015's 1; Buy excludes it |
| D5 | B1, host not found | Buy includes CKSW015's 1 once, under Buy |
| D6 | `kind=buy` filter | B1 row hidden when host is on PO, shown when host is not found |
| D7 | row payload | carries `bundled_qty` and `bundled_with.item_code` (response_model assertion) |
| D8 | export xlsx | bundled row's document column reads the host's code |
| D9 | 375px and 1280px | headline truncates with title, no clipping |

## E. After deploy (no backfill)

| id | given | then |
| --- | --- | --- |
| E1 | open production row, owner unplaces then relinks | `_refresh_link_state` derives `bundled_qty`; SO419595 CKSW015 reads Included with CKS1050 |
