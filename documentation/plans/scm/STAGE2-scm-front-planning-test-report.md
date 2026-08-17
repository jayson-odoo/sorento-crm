# Stage 2 test report - product plan and channel breakdown (AC-H03)

Status: FINAL. Rows marked * were re-proven after the sizing-group freeze fix (worknotes
BE-6) and the 4.4 real-stack re-verify; everything else was green before it and re-run after
(post-merge scoped gate: 250 backend tests passed, FE vitest 1090 passed).

Scope: UAC Groups E (AC-E01..E07) and F (AC-F01..F12) of
`documentation/plans/scm/UAC-scm-front-planning.md`. Stage 3 (reorder-level rollup and the
hardening sweep) is a separate task; AC-F04 and AC-F06 are covered here only to the extent
Stage 2's data model must support / must-not-invent them.

Evidence keys: **pytest** = backend suite (Postgres, prod-copy DB unless stated),
**vitest** = `sorento_crm_frontend` component/hook tests, **browser** = normal-navigation
`agent-browser` run (worknotes section 4.1 mock run, 4.4 real-stack run), **worked case** =
explicit figures reproduced in the worknotes.

| AC | Verdict | Evidence |
|----|---------|----------|
| AC-E01 | PASS | pytest `tests/scm/test_channel_read_model.py` (classification precedence through `_classify_demand`; Project SO publish stamps nothing); re-based `_demand_aggregates` reads persisted `demand_class` only - `test_summary_order_service`, `test_demand_breakdown` |
| AC-E02 | PASS | pytest `test_channel_read_model` (location never classifies; missing class stays unclassified, not a third class); `test_product_grain_summary` unclassified rows |
| AC-E03 | PASS | vitest `SummaryOrderReportView` stacked channel readings (one row per product); browser 4.1 (Project 480 / Retail 186 / Unclass. 12 stacked, drills per channel); legacy stored values kept - `test_order_summary_routes` legacy rows |
| AC-E04 | PASS | pytest `test_channel_read_model` confirmed-leg tests: `project_confirmed_committed` from `projects.order_inquiry_rows` joined through `core_sales_order_line_id`, ORDER/raised only; sheet leg counted once through the sheet arm while undecided (BE-5 worknotes section) |
| AC-E05 | PASS | pytest `test_channel_read_model` + `test_pool_netting_parity::test_a_shared_pool_covers_its_bins_so_nothing_is_bought`: only confirmed Buy bypasses the trigger; the sheet leg stays inside normal netting (regression pair fixed under BE-5) |
| AC-E06 | PASS* | pytest `test_product_grain_summary` / `test_summary_order_service`: MOQ + order multiple applied once to the product total, unclassified never enters `suggested_qty`; real-engine freeze test added with the network-freeze fix pins shared facts counted once |
| AC-E07 | PASS | vitest `DemandDrillPopover` + `SummaryOrderReportView` ledgers; browser 4.1 per-channel drill buttons; pytest `test_order_summary_routes` demand drill re-based on `demand_class` |
| AC-F01 | PASS | pytest `tests/scm/test_plan_grain_policy.py` (admin policy default `product`, applies to runs created afterwards); vitest settings form; browser 4.1 (Settings > General "Plan grain" select; run chip shows the STAMPED grain, Planning mode selector untouched) |
| AC-F02 | PASS | browser 4.1 `?plan_mock=location` + real-stack 4.4: per-location view actionable at Location grain, read+drill at Product grain; pytest `test_plan_grain_policy` decision-grain guards |
| AC-F03 | PASS* | pytest real-engine freeze test (one calculation, two presentations; same frozen inputs both grains); `test_committed_v_migration_chain` pins the view body |
| AC-F04 | DEFERRED (Stage 3, by contract) | Data model support only: per-location `reorder_level` is frozen per recommendation row and surfaced per location in the basis; the product-level sum rollup is Stage 3's deliverable (task brief "Explicitly not yours") |
| AC-F05 | PASS | pytest `test_channel_read_model` / `test_product_grain_summary`: location actionable need = project_need + retail netted need, unclassified excluded in both grains |
| AC-F06 | PASS (by absence) | No level worklist, no product-level winner, no "Needs level" state added anywhere in this branch's diff; pre-existing `needs_level` engine rows are untouched M8/S10 behaviour, not a new state |
| AC-F07 | PASS* | pytest real-engine freeze test: one aggregate product-location row with separate Project / Retail / unclassified columns and single shared stock / SPO / PO / level values; `committed_v` and `net_position_v` cardinality and join keys unchanged (`test_m0_view_correctness`, `test_committed_v_migration_chain`) |
| AC-F08 | PASS* | Was the defect: network-scope runs froze basis locations with no warehouse identity. Fixed (worknotes BE-6); browser 4.4 real-stack locations drill shows named BRW / BRW-BB rows, channel split, shared facts once, "Suggested once at the product: 37", "Chosen: 37", split back to locations |
| AC-F09 | PASS | pytest `test_plan_grain_policy` (stamped once at create from policy, never NULL, later policy edit does not move it; decision write in the other grain rejected; legacy runs accept no decision in either grain - HTTP guard tests in `test_order_summary_routes`); PO worklist grain-scoped (`test_product_grain_summary`) |
| AC-F10 | PASS | pytest `test_plan_grain_policy` durability tests + browser 4.1 legacy scenario (chip "Legacy run", 24 Unavailable channel cells, decision cells read-only, stored values kept) |
| AC-F11 | PASS | Worked case (worknotes 4.1 + pytest `test_product_grain_summary`): Project 1 + Retail 1 across BRW/JB, supplier multiple 10 - one product row suggests 10, not per-location rounding; kg dp-3 case: need 2.5, no constraint, `suggested_qty` 2.5 exactly (not ceiled to 3). `write_rows` derivation replaced: product total through MOQ/multiple once, quantized once at frozen `uom_decimal_places` |
| AC-F12 | PASS | pytest `tests/test_uom_decimal_places.py` (77: 0..4 validation on create/edit/list/detail/select, omitted-create 0, omitted-edit preserves, name-only backfill with greatest-observed-scale capped at 4, no quantity row rewritten); freeze snapshot durability across a UOM downgrade (`test_product_grain_summary`); decimal allocator in integer minor units summing exactly to `chosen_qty` (`test_m4_decisions` + allocator tests); browser 4.1 worked case `SRTAD9002` (kg dp 3: typed 2.75 accepted, split BRW 1.375 / JB 1.375, toast at dp 3) and `SRTTB1120` (dp 0 rejects 2.5) |

Notes:

- The `0` fallback for rollout UOM rows survives the backfill: classification is by name
  only; unknown and count names resolve to 0, and 0 is the column default (worknotes 4.2,
  measured on the prod copy: all 12 units land on 0).
- Known local failures outside this scope are prod-copy data artefacts or pre-date the
  branch (worknotes BE-5 tail); the honest gate is CI's empty database.
