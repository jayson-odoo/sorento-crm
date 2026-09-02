# PLAN: SCM reorder + order-inquiry feedback batch (1 Sep 2026)

Status: S1 IMPLEMENTED (PR #471, 1 Sep 2026) - review found a 6th creation site
(`project_supply_service.py::_place_supply_borrows`) and 6 other must-fix items, addressed on the
same branch. S6 IMPLEMENTED (PR #490, 2 Sep 2026); its first cut answered G12's gate with a
BORN-CLAIMED pass that let the cascade write its own claim, which the captain measured on
real data as theft and WITHDREW the same day - replaced by write-time claiming (G12's own
entry below, plus D2/D3/D4 beneath it). S2-S5 not built.
UAC: `scm-reorder-oi-feedback-1sep-acceptance-criteria.md`

## Journeys

- J1 CS uploads inquiries: rows born confirmed, links written immediately. Purchasing sees
  only exceptions (rejects they issued, changed-row audits, configured change notifications).
- J2 Joey checks an order: opens Order Inquiries (no default filter), searches the SO. Rows
  show only documents genuinely free or dedicated to THIS SO. One decision max: reject.
- J3 Buyer runs a reorder: Start Plan -> plan holds ONLY products with committed demand
  (213 buys on today's data, not 4,255 rows). Every Buy traces to demand. Decisions in-row,
  one Confirm. Wrong horizon or scope -> edit in header tab -> Re-plan carries decisions.
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

- G1 Run universe = COMMITTED DEMAND ONLY. "As long as got committed demand -> into plan,
  simple as that." No movement gate, no activity window: a product row enters the run iff
  committed demand > 0 (acknowledged OI + SO book demand as `demand.py` already defines).
  Retail with no demand = no replenishment - intended; overstock-averse ruling.
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
  - WRITE-TIME CLAIMING (captain, 2 Sep 2026 - this SUPERSEDES the withdrawn
    "born claimed" mechanism, which is deleted, not disabled). The rule, stated
    strictly: the automatic pass may take (a) POOL-location documents and (b)
    project-bin lines explicitly attributed to the row's OWN sales order. It never
    takes a project-bin line that is unattributed or attributed to another SO, and it
    NEVER writes the attribution itself. An own-SO-attributed bin line IS auto-linked -
    forcing a manual click there is busywork.
    Attribution has exactly three sources, none of them the cascade:
      1. the BOOK's `FromSODocList` column - `po_history` on the purchase-history
         channel, `po_upload` on the outstanding channel (D2 below);
      2. the SUPPLY WRITER, at the moment this codebase CREATES the line for known
         demand: `app/services/scm/supply_claim.py`, source `crm_supply`. A reorder
         plan's Confirm lands its buy at a project bin (the buy lands where the demand
         is), so `purchase_order_service.bulk_confirm` claims each project-bin line it
         opens for the order-inquiry rows that sized its `(product, location)` cell -
         in the SAME transaction, never best-effort. One line, several SOs, several
         claims (114 at BRW-IB sized by SO X 30 + SO Y 84 = two claims): ordinary G7
         sharing, not a split;
      3. a PERSON in the Link dialog (`manual` / the placement's own audit row).
    Why the first cut was wrong, measured: PO 202607-S0067's CB1178A-SS-NL at BRW-IB,
    114 units bought for SO391853 per the AutoCount book, was auto-linked to SO381895
    at 2026-09-02 02:47:41 against a claim SO381895 had written for itself moments
    earlier. `_born_claimed_takes`, `_has_external_claim`, `trial_cascadable` and
    `pass_unattributed` are gone; `_candidate`'s `cascadable` is the only gate and has
    no trial variant.
    A blank `FromSODocList` beside a Loading Date remark such as "REPLACE BACK" means
    the line belongs to ANOTHER sales order (captain, 2 Sep) - one more reason
    unattributed reads as locked rather than as free.
    Kept from the first cut, because they were separate, real bugs: `_claims_by_target`
    reading the CLAIM's own `so_number` (not the joined core one), and the netting that
    stops a claim being subtracted twice once its own SO has placed part of it - now
    measured off `OrderInquiryLink.claim_id` rather than guessed from the claim's
    source (`_reserved_for_netting`).
- G13 (2 Sep) THE OUTSTANDING BOOK WRITES CLAIMS (D2). `outstanding_import_service`
  resolved `FromSODocList` and threw the value away, so the feed most attribution
  arrives on could not seed a single dedication. It now writes one `po_upload` claim per
  stated line through the same get-or-create the history channel uses
  (`order_link_service.claim_book_pairing`) and resolves both sides immediately. A
  re-upload restates rather than doubles (identity = company + SO + PO + item), and a
  claim another feed already made keeps ITS source. Alias seeds: migration 456.
- G14 (2 Sep) FREE NETS DEDICATION (D3). The purchase order's "Allocated to" panel read
  `Free = outstanding - links`, so 202607-S0067's BRW-IB line printed Free 69 on a line
  the book dedicated wholly to SO391853 - which is how the same quantity gets bought
  twice. `Free` now also nets what other SOs' claims still reserve (G7: the claiming
  line's LIVE outstanding, less what that claim has already placed), and each block
  names who holds it. A line with a dedication and no placement is a block of its own.
- G15 (2 Sep) THE REPAIR IS A GUARDED ONE-SHOT, NOT A MIGRATION (D4).
  `scripts/repair_project_bin_self_claims.py`, `--scope today|legacy|both`, dry-run by
  default. `today` undoes exactly what the withdrawn pass wrote (an `auto = true` link on
  a project-bin target whose only claims are `order_inquiry` rows from 2026-09-02
  onward, plus those claims). `legacy` extends it to every other automatic project-bin
  placement no EXTERNAL claim names the row's own SO for. A human link (`auto = false`)
  is never touched in either scope; a row that loses every link returns to uncovered,
  which is intended. NOT run by `alembic upgrade`: `legacy` requires a fresh upload of
  the current PO & SPO outstanding book FIRST, or it drops links that book would have
  justified. Prod sequence: deploy -> captain re-uploads the book -> run `--scope legacy
  --apply`. Dev (2 Sep): `today` applied, 22 links + 11 claims deleted; `legacy` dry-run
  then reported 2 links / 1 row / 2 claims still to go, awaiting the book upload.
- G8 Re-plan: Plan until AND warehouse/product scope editable. New run supersedes old;
  decisions carry for products present in both runs with unchanged suggestion; leaving scope
  drops them; entering arrives undecided; changed suggestions return flagged "re-check".
- G9 Segments: full recursive nesting (groups in groups, any depth); a segment stores the
  FULL view (filters + sort + visible columns + order); surfaced as a dropdown beside
  Filters (NOT chips); per-user default + shared/published default, one-default rule and
  publish permission mirroring report views. v1 field descriptor as listed in S4.
- G10 Explicit product selection at Start Plan bypasses the committed-demand gate (named
  product = buyer intent).
- G11 S3 perf quick wins approved as listed.

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
- `_planning_rows` (`reorder_run_service.py:531`) restricted to product x location rows with
  committed demand > 0 within the run horizon (same committed SELECT the engine already
  uses); explicit `product_ids` bypass the gate (G10).
- Disposition/dead-stock emission removed from the run (G2); backlog item for the report.
- `needs_level` remains ONLY for committed products missing a level.
- Goldens re-pinned. Expected: ~213 buys + their covered/needs_level rows, a few hundred
  total.

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
- v1 fields: product code/name, category, supplier, location, rec type, decision state,
  suggested qty, reorder level, reorder qty, on-hand BRW, SPO qty, PO qty, project
  committed, retail committed, unit cost, currency, days late.
- First consumer: plan grid (`scm.dashboard.view::reorder-plan-lines`).

### S5 - Plan detail tabs + Re-plan
- Header tab (Plan until, warehouse/product scope, cut-off, status, counts) + Lines tab.
  View = edit layout.
- Editing Plan until OR scope offers Re-plan (G8): POST creates a NEW run, supersedes the
  old (two-way link, list label), carries decisions per G8's rule, "re-check" flag on
  changed suggestions.

### S6 - Dedication-aware OI takes (claims)
- `_candidates_for_row` consults `scm.order_link_claim` per G7: other-SO claims subtract
  (SO-date order, live outstanding); fully-claimed lines never auto-taken; own-SO claim
  ranks first; greyed "Dedicated to SO xxxx" with manual override. Unresolved claims match
  by (po_number, item_code). SPO leg via `spo_allocation_id` claims.
- G12 project-bin lock: cascade skips ANY project-bin line not claimed by the row's own SO
  (claimed-by-other AND unclaimed alike); dialog shows unclaimed project-bin lines greyed
  "Unattributed - link manually"; manual link writes the claim. Unclaimed-project-bin
  counts on the PO/SPO upload result and as a PO-view filter for Joey's backfill.
- Write-time claiming (`app/services/scm/supply_claim.py`, source `crm_supply`), the book's
  own `FromSODocList` on the outstanding channel (`po_upload`), dedication netted out of the
  PO detail's Free, and the one-shot repair: G12's own entry above plus G13/G14/G15.

## Build order

S1 -> S2 -> S3 -> S6 -> S4 -> S5. S4/S5 get lavish mockups before build (captain: lavish is
for mockups after decisions; grilling happens in the terminal).

## Non-goals

- No change to location tiers / Q5 ranking.
- No re-run-in-place (immutability stays; Re-plan supersedes).
- No server-side filter evaluation for the plan grid.
- No movement/activity-window machinery (G1 made it moot); no dead-stock surface in the
  plan (report is backlog).
