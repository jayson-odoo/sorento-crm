# PLAN: SCM reorder + order-inquiry feedback batch (1 Sep 2026)

Status: S1 IMPLEMENTED (PR #471, 1 Sep 2026) - review found a 6th creation site
(`project_supply_service.py::_place_supply_borrows`) and 6 other must-fix items, addressed on the
same branch. S2 (engine scope) built on `feat/reorder-committed-only`, PR #488 -
re-reviewed 2 Sep: G1 reworked from row-grain to PRODUCT-GRAIN admission (a product with
committed demand anywhere among its own locations admits all its rows; a location-grain
basis gates EMISSION per location instead) after a review found the row-grain cut broke
pooled netting (B1 regression). Merge-ready pending CAPTAIN CONFIRM of the product-grain
reading (2 Sep intent ruling, not yet signed off in the terminal). S4 (dynamic filter +
segments) built on `feat/dynamic-filter-segments`, PR #489 - review round 2 Sep added
company-scoping to `saved_views` and a fail-closed permission default on its routes,
pending captain confirm. S3 (perf quick wins) built on `feat/reorder-perf-quickwins`, PR
#491 - review fix round amended AC-3.4's `plan_basis` claim to the measured numbers (see
S3 below). S5 (plan detail Header/Lines tabs + Re-plan supersede) built on
`feat/reorder-replan`, PR #493 (stacked on S2), review round 1 addressed - see the S5
section's own note on the one OPEN ruling (confirmed/keyed decisions block a Re-plan
outright; captain confirm pending). All six slices built, PRs open as of 2 Sep 2026:
S1 #471, S2 #488, S3 #491, S4 #489, S5 #493, S6 #490. Merge order: #471 -> #488 -> #489 -> #491 -> #490 -> #493 -
S3/S4/S5/S6 each stack a migration onto 453/454/455 in turn (see
`456_reorder_perf_quickwins`'s own docstring for the two-round renumbering this caused).
UAC: `scm-reorder-oi-feedback-1sep-acceptance-criteria.md`

## Journeys

- J1 CS uploads inquiries: rows born confirmed, links written immediately. Purchasing sees
  only exceptions (rejects they issued, changed-row audits, configured change notifications).
- J2 Joey checks an order: opens Order Inquiries (no default filter), searches the SO. Rows
  show only documents genuinely free or dedicated to THIS SO. One decision max: reject.
- J3 Buyer runs a reorder: Start Plan -> plan holds ONLY products with committed demand
  (~201 buys / ~830 rows on today's data - measured 2 Sep, post product-grain fix - not
  4,255 rows). Every Buy traces to demand. Decisions in-row, one Confirm. Wrong horizon
  or scope -> edit in header tab -> Re-plan carries decisions.
- J4 Buyer slices the plan: composes filters, saves as a segment, optionally shares; next
  visit one click from the views dropdown.

## Measured facts (prod-copy DB, run c9c575c8)

- 4,255 rows = 1,650 disposition + 1,528 needs_level + 668 buy + 409 covered.
- Buys: 213 committed>0, 114 movement-only (no SO), 71 both, 341 zero-everything
  (AutoCount-level artifacts; 11,007/11,009 stored levels have source='autocount').
- Engine has no demand gate (`reorder_engine.py:302` trigger = `net <= level`); run universe =
  every stock row (`reorder_run_service.py:531`).
- OI takes at BRW-IB: location correct (tier 1, Q5 25 Aug). Gap = dedication: candidates net
  OI links only (`project_order_inquiry_service.py:2812`), never `scm.order_link_claim`
  (33,231 po_history claims from the PO/SPO book's FromSODocList column, 20,841 resolved).
- Perf: decisions N+1 on unindexed `purchase_order_lines.source_ref`; plans-list counts join
  the whole PO-lines table; detail downloads ~9-12 MB over ~13 requests (pool 10+20).
- Runs immutable (`plan_horizon_date` stamped once, no refresh route).
- Manual relink for mistakes already exists (`place-on-po` with allocations rewrites links).
- Automations surface: `automations` table (trigger_type + trigger_config, recipient_config
  {user_ids, role_ids}, rule-engine conditions, templated email; in-app per channel toggles).
- Dead stock = `dead_stock_days` policy (180): no movement in window / bought-never-moved.

## Rulings (captain, 1 Sep 2026 - three grill rounds)

- G1 Run universe = COMMITTED DEMAND ONLY, admitted at PRODUCT GRAIN (captain-intent
  ruling, 2 Sep - PENDING CAPTAIN CONFIRM, supersedes the row-grain reading S2 shipped
  first). "As long as got committed demand -> into plan, simple as that" is a statement
  about the PRODUCT: a product with committed demand > 0 ANYWHERE among its own
  locations (acknowledged OI + SO book demand as `demand.py` already defines) admits ALL
  of that product's location rows, so an aggregate basis (pooled netting, a network-scope
  buy, the product-wide `reorder_level` basis) keeps every location's on-hand/on-order in
  its net - a location with none of the committed demand itself is still real SUPPLY an
  aggregate is entitled to see. The pool's own BUY (allocation/placement) and `covered`
  rows are POOL-level decisions and stay unfiltered by a member's own commitment - that
  is the fix, not a second gate on top of it.

  WHICH locations get their OWN recommendation row is separate, and the gate differs by
  shape: `reorder_run_service._emit_cell` (a location that is not pooled with anything)
  withholds its WHOLE cell - buy, covered, needs_level alike - when the location carries
  none of the product's committed demand, G10-named products exempted (see G10).
  `_emit_pool`'s `unset` loop withholds `needs_level` ONLY, per pooled member - the
  pool's own buy (allocation/placement) and `covered` rows stay POOL-level aggregate
  decisions, unfiltered by any one member's commitment (that visibility is the fix
  itself). `_plan_network` carries no such gate at all - the reorder_level policy_type it
  would apply to is caught earlier, by `_is_product_level_basis`, which routes the WHOLE
  product to `_emit_product` first; the code that would have gated it there was dead by
  construction and removed 2 Sep. No movement gate, no activity window either way. Retail
  with no demand anywhere = no replenishment - intended; overstock-averse ruling.

  Row-grain admission (S2's first cut, corrected 2 Sep) stripped an uncommitted
  location's on-hand/on-order from every aggregate reading it - on the dev-DB
  full-network run, 76,098 on-hand + 14,475 on-order units lost from 298 in-plan
  products' aggregates, 55 `covered` rows flipping to `buy` and 37 buys inflated by
  2,032 units net. The exact SRTWT7408 shape ("1,296 at the pool root, nothing at nine
  group bins") ADR-0011's pooled netting exists to solve, because a customer's SO names
  the BIN, never the pool ROOT - so the root is almost always zero-committed itself. Two
  hand-written per-row exception joins (pool-root supply, unlocated demand) patched
  around that mistake in the row-grain cut; both are deleted under product-grain
  admission - a product whose entire demand is unlocated already has committed > 0 on
  its own row of the product-only admission check, so it needs no second join either.
  RE-ADD TRIGGER: if a future change ever narrows admission back to row-grain (unlikely -
  it broke pooled netting outright), the unlocated-demand join is the one piece that
  would need to come back, since `_apply_unlocated_demand` lands unclaimed demand on
  "the location holding the most of the item" only when every row of that product is
  still in the run to choose from.
- G2 Dead stock / disposition rows leave the plan entirely. Dead-stock + overstock report
  goes to the reporting-foundation backlog (`documentation/backlogs/backlog.md`).
- G3 Zero-movement machine-level rows: excluded (subsumed by G1).
- G4 Auto-ack: rows born acknowledged; `changed` auto-acks too; reject is the only manual
  gate; system attribution when no actor; BACKFILL all existing awaiting rows at migration.
- G5 OI page: no default ack filter (filter stays available for rejected/changed lookups).
- G6 Change notification = new automation trigger type `order_inquiry_changed_with_links`
  (fires only when the changed row already has links). Recipients + channel configurable via
  the existing automations surface (recipient_config role/user, email template, conditions
  tree, in-app per channel toggles). Nothing hardcoded.
- G7 Dedication (S6): explicit claims only, never the assignment walk. A claim reserves the
  claiming SO line's FULL quantity from that PO line; leftover PO quantity stays free
  (PO 100, SO A 30 claimed -> 30 reserved, 70 free; +SO B 50 -> 80 reserved, 20 free).
  Multiple claims reserve in SO-date order. Reservation reads the SO line's LIVE outstanding
  (fulfilled/cancelled -> reserves 0); claim rows never deleted. Own-SO claim ranks first;
  other-SO-claimed lines greyed "Dedicated to SO xxxx" in the Link dialog, manual override
  stays. Location tiers unchanged (Q5 stands).
- G12 (round 4) PROJECT-BIN SUPPLY IS LOCKED: a PO/SPO line destined for a project bin
  (BRW-IB / BRW-BB / any `segment='project'` warehouse) is auto-taken ONLY by the SO that
  claims it. An UNCLAIMED project-bin line is manual-link only (greyed "Unattributed -
  link manually" in the dialog); a manual link writes an order_inquiry claim, converting
  it to claimed. Pool-destination documents keep today's rules. Safe against double-buying
  because the reorder engine nets open PO qty by location regardless of claims - the
  unclaimed line still counts as supply in the plan; only the OI cover state waits for
  attribution. The import result + PO view surface the unclaimed-project-bin count so Joey
  backfills FromSODocList in AutoCount.
- G8 Re-plan: Plan until AND warehouse/product scope editable. New run supersedes old;
  decisions carry for products present in both runs with unchanged suggestion; leaving scope
  drops them; entering arrives undecided; changed suggestions return flagged "re-check".
- G9 Segments: full recursive nesting (groups in groups, any depth); a segment stores the
  FULL view (filters + sort + visible columns + order); surfaced as a dropdown beside
  Filters (NOT chips); per-user default + shared/published default, one-default rule and
  publish permission mirroring report views. v1 field descriptor as listed in S4.
- G10 Explicit product selection at Start Plan bypasses the committed-demand gate (named
  product = buyer intent) - BOTH halves of it (2 Sep clarification): the named product
  is admitted regardless of committed demand (as before), AND each of its rows is
  exempted from the location-grain EMISSION gate G1 added, so a named zero-committed SKU
  gets the same full evaluation (stock/forecast trigger, `needs_level`) it had before G1
  existed - not merely a silent presence in the run.
- G11 S3 perf quick wins approved as listed.

### PR #489 review round (2 Sep 2026) - pending captain confirm

Two additions to G9, applied per the repo's standing fail-closed doctrine rather than a
fresh grill - **pending captain confirm 2 Sep**. (Numbered "S1"/"S2" below refer to this
review round's own two items, not the OI-slice S1/S2 elsewhere in this document.)

- S1: `saved_views` gets `CompanyScopedMixin` + `company_id`. A shared/published
  segment's `view` blob can name another company's suppliers/products/warehouses inside
  its filters, and the listing key alone does not stop that crossing a company boundary.
- S2: on the saved-views routes ONLY, `_can_view_listing_key`'s unknown-permission-slug
  fallback goes fail-closed (403) rather than the permissive "module-auth only" default -
  a saved view is a shared, cross-user surface, unlike column-config's per-user blob
  (which keeps the permissive fallback).

## Slices

### S1 - OI auto-acknowledge
- Rows born `acknowledged` at all 6 creation sites (import
  `project_order_inquiry_import_service.py:864`, board raise `_handshake_for_raise` `:755`,
  cancel-balance `:679`, borrow shortfalls `:1045`, amendment `_write` `:1263`, borrow-asker
  row `project_supply_service.py::_place_supply_borrows` `:5399` - found in review, missed
  in the original grill). System attribution when no actor.
- Amendment/supersede still stamps `changed` + was/now audit, then auto-acks (G4).
- Migration backfills every existing `awaiting` row to `acknowledged` (G4).
- Remove Confirm action (`OrderInquiriesClient.tsx:1290-1341`) and Confirmed column
  (`orderInquiryWorklistColumns.tsx:524-536`); rejected reason + Was/Now move to the
  qty/status cell. No default ack filter (G5). Drop the awaiting chip on the reorder plan.
- New automation trigger `order_inquiry_changed_with_links` (G6): emitted when a row with
  links is amended; visible in the automations UI with recipient_config + conditions.
- Reject flow unchanged. Acknowledge endpoint kept, guard tolerant of the born-ack world.

### S2 - Engine scope: committed-demand-only universe
- `_planning_rows` (`reorder_run_service.py`) admits a PRODUCT (all of its rows) when it
  has committed demand > 0 at any of its own locations within the run horizon (same
  committed SELECT the engine already uses); explicit `product_ids` bypasses the gate
  entirely (G10, both admission and emission - see G10). Corrected 2 Sep from a row-grain
  gate that broke pooled netting (B1 regression, see G1).
- The location gate that actually ships is narrower than "every emission, per location":
  `_emit_cell` (single, non-pooled location) withholds its ENTIRE cell - buy, covered,
  needs_level alike - for a location carrying none of the product's committed demand
  (G10-named products exempt). `_emit_pool`'s `unset` loop withholds `needs_level` ONLY,
  per member - the pool's own BUY (allocation/placement across members) and `covered`
  rows are POOL-level aggregate decisions and are NOT filtered by a member's own
  commitment, on purpose (that visibility is the B1 fix). `_plan_network` carries no
  per-member gate of any kind: the reorder_level policy_type it would apply to is always
  caught earlier by `_is_product_level_basis`, which routes the whole product to
  `_emit_product` first, so the code that would have gated it there was dead by
  construction - removed 2 Sep rather than documented as reachable.
- A location-grain cell classified dead/overstock that still carries committed demand
  emits `covered` (not silence) in `_emit_cell` - G2 removed the `disposition` rec type,
  but the demand itself must not vanish.
- Disposition/dead-stock emission removed from the run (G2); backlog item BL-045 for the
  report.
- `needs_level` falls out of G1/G10 with no separate gate beyond the location gate above:
  a committed product-wide row (product-grain basis) or a committed member (location-grain
  basis, `_emit_cell` or a pooled member) is the only thing that can reach it; a G10-named
  zero-committed product also reaches it (buyer intent).
- Goldens re-pinned; new dedicated file `tests/scm/test_reorder_committed_universe.py`
  (AC-2.1-2.4, incl. the B1 regression pin - product-level basis with stock at an
  uncommitted location keeps that stock in `agg_net`).
- Measured, post product-grain fix (2 Sep): see the PR body / commit for the exact
  full-network row and buy counts - "a few hundred, not thousands" (AC-2.5) either way;
  the 1 Sep "measured facts" ~213 figure predates both this fix and a day of data drift
  on the shared dev DB, so it is a ballpark, not a pinned number.

### S3 - Perf quick wins (approved)
- Migration: index `purchase_order_lines (source_ref, source_system)`.
- `list_plan_row_decisions`: constant query count (joined supplier + grouped PO map).
- Denormalise planned/decided/confirmed counts onto `scm.reorder_run`; list + Decided sort
  read the columns.
- `list_recommendations`: drop `plan_basis` from the payload; precompute pool warehouse
  id/code at run time (kills the per-row LATERAL).
- FE: no full decisions refetch per decision; `groupPlanLinesByChannel` runs once.

### S4 - Dynamic filter + saved segments (reusable)
- `<DynamicFilterBuilder>`: field + operator + value rows (equals, contains, in-list, >, <,
  between, is-empty), AND/OR toggles, fully recursive groups (G9). Wire shape =
  `ListQueryFilterGroup`/`ListQueryFilterCondition`. Fields from a TS descriptor beside the
  column defs; client-side `evaluate(group, row)`.
- Segments = full views (filters + sort + columns, G9): generalise `report_views` ->
  scope-keyed `saved_views` keyed by listing key; port `views_service.py` (one-default race
  guard, publish permission); lift `ReportViewsMenu` -> generic `<SavedViewsMenu>` dropdown
  beside Filters. Auth via `_can_view_listing_key`.
- v1 fields: product code/name, supplier, location, rec type, decision state, suggested
  qty, reorder level, reorder qty, on-hand BRW, SPO qty, PO qty, project committed,
  retail committed, unit cost, currency (16 fields; PR #489 review round S7 dropped
  category and days late - neither has a data source on `PlanLine`, so both would have
  shipped as a dropdown entry that could only ever match "is empty").
- First consumer: plan grid (`scm.dashboard.view::reorder-plan-lines`).

### S5 - Plan detail tabs + Re-plan
- Header tab (Plan until, warehouse/product scope, cut-off, status, counts) + Lines tab.
  View = edit layout.
- Editing Plan until OR scope offers Re-plan (G8): POST creates a NEW run, supersedes the
  old (two-way link, list label), carries decisions per G8's rule, "re-check" flag on
  changed suggestions.
- OPEN RULING (review round 1, flagged for captain confirm - built conservative pending
  the answer): `replan_run` currently REJECTS (422) a run carrying any CONFIRMED (draft PO
  line already written) or KEYED (`keyed_status`/`OrderSummaryRow.chosen_qty`) decision -
  re-planning it would hand `confirm_decisions` a run whose recs carry brand-new ids,
  orphaning the existing draft line and inviting a double-key into AutoCount from two
  different plans. The captain may instead want that state CARRIED forward onto the new
  run rather than blocked outright - not built; `decision_service.has_confirmed_or_keyed_decisions`
  is the one call site to change if so.

### S6 - Dedication-aware OI takes (claims)
- `_candidates_for_row` consults `scm.order_link_claim` per G7: other-SO claims subtract
  (SO-date order, live outstanding); fully-claimed lines never auto-taken; own-SO claim
  ranks first; greyed "Dedicated to SO xxxx" with manual override. Unresolved claims match
  by (po_number, item_code). SPO leg via `spo_allocation_id` claims.
- G12 project-bin lock: cascade skips ANY project-bin line not claimed by the row's own SO
  (claimed-by-other AND unclaimed alike); dialog shows unclaimed project-bin lines greyed
  "Unattributed - link manually"; manual link writes the claim. Unclaimed-project-bin
  counts on the PO/SPO upload result and as a PO-view filter for Joey's backfill.

## Build order

S1 -> S2 -> S3 -> S6 -> S4 -> S5. S4/S5 get lavish mockups before build (captain: lavish is
for mockups after decisions; grilling happens in the terminal).

## Non-goals

- No change to location tiers / Q5 ranking.
- No re-run-in-place (immutability stays; Re-plan supersedes).
- No server-side filter evaluation for the plan grid.
- No movement/activity-window machinery (G1 made it moot); no dead-stock surface in the
  plan (report is backlog).
