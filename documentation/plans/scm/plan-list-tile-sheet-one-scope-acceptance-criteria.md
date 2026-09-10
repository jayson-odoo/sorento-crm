# UAC - the plan list, the decisions tile and the order sheet share one scope

Plan: `PLAN-plan-list-tile-sheet-one-scope.md` (same folder).
Owner ruling, 10 Sep 2026: "tile counts what the list show, and the exported excel should be
faithful to the list also." Supersedes the #795 line "the order sheet prints every planned
product" for rows the list hides.

## Journey

The buyer opens a plan. The Decisions tile says how many rows are on the list to decide, the
list shows exactly those rows, and Actions > Order sheet prints exactly those rows. A covered
row on the manual reorder-level basis whose net sits above its level is "not my business"
(owner, 12 Aug 2026) and appears in none of the three unless the buyer asks for it with the
"Covered by stock" status filter.

Measured (local prod copy, plan of 10 Sep 19:39): 950 recs = 412 Buy + 537 Covered + 1 Needs
level; the list shows 415 (412 + 1 + 2 breached covered rows), the tile says "0 of 950", the
sheet prints 950 rows.

## The one rule

`hidden_by_default(rec)` is true when ALL hold: `rec_type == covered`, the basis is manual
(`inputs.policy_type == 'reorder_level'`), the basis value exists (`inputs.reorder_level`, else
the product's master level), the net exists, and `net > basis`. A missing basis or net means
shown (the frontend's `lineBreachStatus` treats it as breached). Today that rule is spelled
once, in `PlanLinesSection.visibleLines` + `orderQtyLedger.lineBreachStatus` (frontend). It
moves to ONE backend function and the three readers use it; the frontend stops recomputing.

## Phase 2 - backend, test-first

- **AC-1 [BE]** `GET /reorder-runs/{run}/recommendations` rows carry `hidden_by_default:
  bool`. Given a covered manual-basis rec with net 1,447 and level 50, then true; the same
  rec with net 40, then false; a covered rec on the auto basis (`reorder_point`), then false;
  a Buy rec, then false; a covered manual rec with NO level anywhere, then false.
- **AC-2 [BE]** `GET /reorder-runs/{run}/plan-row-decisions` `total_decidable` excludes
  hidden-by-default rows: on the seed above (1 Buy + 1 hidden covered + 1 shown covered),
  `total_decidable == 2`. `decided` counts a decision on a hidden row all the same (it was
  reached through the filter), so `decided <= total_decidable` is NOT asserted.
- **AC-3 [BE]** `export_report` (PDF and XLSX) omits hidden-by-default rows: the seed prints
  2 rows, not 3; the row-count guard (`export_guard_stats`) counts the same 2.
- **AC-4 [BE]** The sheet's frozen `order_summary_row` keeps every product (the report
  endpoint is unchanged); only the export and the count read the rule.
- **AC-5 [FE]** `PlanLinesSection.visibleLines` hides on `rec.hidden_by_default` and drops
  `lineBreachStatus` from that path; the "product's own row stays while the product is on the
  plan for another reason" exception is unchanged. The "Covered by stock" status filter still
  shows every covered row.
- **AC-6 [FE]** Decisions tile reads "0 of 415 made / 415 left to decide" on the measured
  plan (server count, unchanged wiring).
- **AC-7 [E2E]** Same plan: list total 415, tile 415, Excel row count 415, and B2154-NL
  appears in none of the three by default and in the list under the "Covered by stock"
  filter.

## Out of scope

- Reversing the 12 Aug hiding rule.
- Any new column, flag or setting.
