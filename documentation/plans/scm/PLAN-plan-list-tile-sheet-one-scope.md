# PLAN - the plan list, the decisions tile and the order sheet share one scope

Status: building (10 Sep 2026) - owner ruling given, then "can we combine with 828?": folded
into PR #828 on the same lane (issue #829).
UAC: `plan-list-tile-sheet-one-scope-acceptance-criteria.md` (same folder).
Domain: scm. Lane branch: `feat/po-spo-site-pool-downloads` (PR #828), slices S6-S8 there.

## Problem, measured

Plan of 10 Sep 19:39 on the prod copy: 950 recs; the list shows 415 because
`PlanLinesSection.visibleLines` (frontend) hides covered manual-basis rows whose net sits
above the level (owner rule, 12 Aug 2026). The Decisions tile reads "0 of 950" because its
total is the server's (`GET .../plan-row-decisions`, `usePlanLines.totalDecidableCount`)
and the server does not know the rule. The order sheet prints 950 because `export_report`
prints every `order_summary_row` (#795 "every planned product"). Three readers, two scopes.

## Design - simplest thing that works

One backend function, three callers. No column, no flag, no setting.

- `app/services/scm/plan_scope.py`: `hidden_by_default(rec_type, policy_type, reorder_level,
  master_reorder_level, net) -> bool`, the exact twin of the frontend's
  `lineBreachStatus` + `visibleLines` predicate (covered AND manual basis AND basis present
  AND net present AND net > basis). One place; the docstring quotes the 12 Aug ruling.
- Recommendation serializer (`reorder_run_service`, the `recommendations` list route): add
  `hidden_by_default` to each row (`response_model` must declare it, or it is dropped
  silently - repo lesson). Inputs already on the rec: `rec_type`, `inputs.policy_type`,
  `inputs.reorder_level`, `master_reorder_level`, `net_position` (+ `po_ordered`, the same
  `net` the ledger shows - confirm which value the FE's `l.net` is and use that one).
- `plan-row-decisions` total: exclude rows where the function is true.
- `summary_order_service.export_report` and `export_guard_stats`: skip the same rows. The
  frozen `order_summary_row` and the report endpoint are untouched (AC-4); the sheet stays
  "the plan row I would see", which is what the buyer meant.
- Frontend: `visibleLines` filters on `l.rec.hidden_by_default`; keep the "product's own row"
  exception; delete the client-side breach recomputation from that path only
  (`lineBreachStatus` stays for the ledger sentence).

## Slices

| Slice | Scope | Phase |
| --- | --- | --- |
| S6-FE | `visibleLines` reads the flag (mock the field on fixtures) | 1 |
| S6 | `plan_scope.py` + serializer field + response model | 2, tester-first |
| S7 | `plan-row-decisions` total + export/guard skip | 2 |
| S8 | reviewer re-pass + browser AC-7 | 3 |

## Captain's test list

- AC-1 `test_hidden_by_default_flag_on_recommendation_rows` (five cases in one parametrised test).
- AC-2 `test_plan_row_decisions_total_excludes_hidden_rows`.
- AC-3 `test_export_omits_hidden_rows_and_guard_counts_the_same` (xlsx row count + guard).
- AC-4 `test_report_endpoint_still_lists_every_product`.
- AC-5 vitest `PlanLinesSection.visibleLines.test.tsx`: hides on the flag, filter shows all, own-row exception intact.
- AC-7 browser: list total, tile, Excel row count all equal; B2154-NL absent by default.

## Backlog

- Sheet "Dealer o/s" vs grid "Retail" ruling (still parked, from the #828 lane).
