# PLAN - Purchasing side: the journey from order inquiry to confirmed PO, and the UAT fixes on the reorder plan

Status: IN PROGRESS r5, 2026-08-26. P1, P5 and P6 are BUILT on branch `feat/scm-uat-plan-page-p1-p5-p6` (stacked on `feat/scm-uat-popover-locations`, PR #310) and verified in the browser on :3080. P3, P4, P7 and P8 are BUILT on `feat/scm-uat-plan-p3-p4-p7-p8` (stacked on `feat/scm-uat-po-occupancy`, PR #325): migrations 424 (committed_v loses the sheet leg) and 425 (every NULL demand_class stamped retail, reversible through `scm.demand_class_backfill_425`) are written and NOT yet applied to the dev copy, so five engine tests that read the real `scm.committed_v` stay red until they are. P2 still awaits go. Part 2 of `PLAN-scm-cs-planning-uat.md` (part 1 = CS). Captain: "I need the user journey crafted out and aligned before we execute anything." Nothing here is built until the journey below is agreed.
Lane: `.claude/worktrees/scm-uat`, FE :3080, BE :8080.

## 1. The journey (target state, one line per hand-off)

| # | Who | Does | System records | Next reader sees |
| --- | --- | --- | --- | --- |
| 1 | CS | Approves a sales order on the fulfilment board | decision revision; OI ORDER rows for every Buy (one row per SO line, full qty); a Transfer for every reserve from elsewhere (part 1 E) | OI worklist: raised rows, Raised by CS name + time; Transfers page: proposed moves |
| 2 | System | Auto-link runs on confirm | for each raised row: open PO lines, location tiers (same location, same group other site, pool, sibling), PO date first (issue date, then line expected date); partial allowed. **SPO allocations are candidates ONLY for an ORDER BACK row** (captain, 25 Aug): a row CS marked as order-back, the form's "ORDER BACK" with the cited PO/SPO in the remark | OI row: Linked n of q, partly linked or linked; PO detail: Allocated to; SO detail: Linked to |
| 3 | System | Daily plan (or the buyer's manual plan) | PROJECT demand = the UNLINKED remainder of raised OI ORDER rows, per product and location. Nothing else project-class counts. RETAIL demand = the SO book directly. Supply = free stock + `spo_allocations` incoming. Outstanding PO is NOT supply for project (it was consumed in step 2); for retail it nets as on-order | Reorder plan: Project column = what CS asked for minus what is already on a PO/SPO; Retail column = book |
| 4 | Buyer | Accepts / adjusts / skips per row | plan_row_decision; draft PO per supplier with the buy lines | PO list: draft |
| 5 | Buyer | Confirms the draft PO | PO active, canonical number; auto-link runs again with trigger `po_confirm`: the new PO lines link to the raised rows whose remainder sized the buy (same product, location tiers) | OI worklist: those rows read Linked to PO-2026/08-nnnn; PO detail: Allocated to lists them with the needed-at location |
| 6 | Buyer | Keys the PO into AutoCount per the Split for AutoCount text, uploads the PO book | import matches lines by (product, warehouse) then line_no, in place; links survive; a still-open remainder is re-linked by the cascade | OI, PO, SO all agree |
| 7 | Purchasing | Uploads SPO / shipping order | one `spo_allocations` row per SPO line (part 1 K) | ladder rung 1 fires; Link SPO has rows; reorder plan sees incoming |

The rule that makes the loop close: **a project requirement lives in exactly one place at a time** - on the board until approved, on a raised OI row until linked, on the PO/SPO once linked. Reorder planning reads the middle state only.

## 2. What the captain saw on the reorder plan, and why (verified 25 Aug on runs b805ba89 and 93305b25)

| Seen | Cause | Fix |
| --- | --- | --- |
| M310-CR-PJ shows Project demand at BRW-BB although every OI row for it is placed | `committed_v` has TWO project legs: the confirmed leg (raised OI ORDER rows, `project_confirmed_committed`, = 0 here, correct) and the SHEET leg: open lines of project-class orders whose `demand_origin = 'scm_order_inquiry'` (the old Joey-sheet feed) with no active decision. SO394803 line 10 + SO411133 line 6 at BRW-BB = 16 project committed. Those two orders came in through the sheet months ago and nobody has confirmed them on the board. | **Retire the sheet leg for project class** (P3). Project demand = confirmed leg only. Sheet-origin project orders without a decision are "awaiting CS", reported by `set_aside_project_demand`, never netted. `committed_v` migration, `reorder_run_service` reads `project_confirmed_committed` only, `project_sheet_need` goes. |
| MSK11B shows many BRW-BB / BRW-IB demand lines while the OI page has two rows | Same: 243 at BRW-IB is SO409325's sheet-origin lines; the two OI rows (13 + 13) are the confirmed leg (26 at BRW-BB). | P3 |
| "Why does reorder planning consider outstanding PO again when the OI already links to it?" | Two mechanisms overlap: OI links retire demand on the OI side, and the S15 "Use PO" cover offers the same PO on the plan side. For project lines that is double handling. | **Project lines: no PO in the plan** - a PO is consumed by links only. **Retail lines: keep "Use PO"** (retail has no OI, so the plan is where a PO meets its demand). Cover-sources endpoint filters by channel. |
| Manual plan: empty warehouses blocks with "Select at least one warehouse" while empty products means all | `RunPlanningModal.tsx:103` | P1: empty = every warehouse, same help text as products; Select all link stays. |
| Plan page slow in production | The page fetches ten run-wide sidecars, none paged: on b805ba89 (5,511 recs) trajectory 2.6 MB, level-suggestions 3.2 MB, purchase-trend 2.6 MB, recommendations (500) 2.1 MB, price-history 1.35 MB, cover-sources 0.7 MB, product-economics 0.8 MB, po-book 0.3 MB: ~14 MB JSON (gzip is on, ~1.5-2 MB on the wire) plus serialisation time. Local BE answers in 0.03-0.72 s each; production adds a remote DB and a slower box. | P2: scope every sidecar to the visible page (`?rec_ids=` of the current page, refetched on page/filter change, cached per run) instead of the whole run; keep whole-run only for the summary counts. Add per-endpoint timing to the logging middleware so production numbers are known, not guessed. Target: first useful paint under 2 s on an 8,000-row run. |
| Unclassified column | Shown whenever any visible row has `unclassified_committed`. Captain: "nothing should be unclassified". | P4: column removed. `demand_class IS NULL` counts in the retail leg (retail is the book-direct channel) and the SO import warns per unclassified order so the source gets fixed. |
| Order history popover carries both "Project, last 12 full months" and "Retail, last 3 full months" | `DemandContextHeader` renders both badges regardless of channel. | P5: one badge, the row's channel only. |
| "Consider 490 more - orders rose 3233%" | `PlanLineDecisionCell.tsx:326` trajectory advice line. | P6: remove the line; the trajectory popover keeps the sentence. |
| After generating a PO from the plan, confirming it must tie back to the order inquiry | `bulk_confirm` already runs the auto-place cascade (trigger `po_confirm`); it links the earliest open line by expected date, which may not be the rows that sized this buy. | P7: on `po_confirm`, link first the raised rows whose product and location sized the confirmed lines (the plan row's demand breakdown knows them), then cascade the rest. PO detail shows the result immediately (part 1 G). |

## 3. Workstreams

- **P1** Manual plan warehouses optional (FE, one hour).
- **P2** Plan page load: paged sidecars + timing log (BE + FE, two days). Measured first on production with the timing log for one day before the FE change, so the fix targets the real cost.
- **P3** Project demand = OI only: `committed_v` migration (sheet leg removed for project class, unclassified folded into retail), `reorder_run_service` simplification, `set_aside_project_demand` reports sheet-origin orders awaiting CS, plan Project column tooltip "what CS asked for, less what is already on a PO or SPO" (BE, two days). Golden set changes; the M3 parity tests are re-baselined with the captain's sign-off.
- **P4** Unclassified column removed + import warning (FE + BE, half a day).
- **P5** History popover channel wording (FE, one hour).
- **P6** Trajectory advice line removed (FE, half an hour). DONE. Observed while verifying: the SO column that carries the trend popover renders only when the grid is NOT grouped by channel (`PlanLinesGrid`, `!groupByChannel`), and every front-planning run groups by channel - so after P6 the demand trend has no surface on the grid at all. Needs a captain call: either bring the popover onto a channel column, or accept that the trend is read elsewhere.
- **P7** Confirm-PO links to the rows that sized it (BE, one day; depends on part 1 I links table).
- **P8** Cover sources: "Use PO" retail only (BE + FE, half a day).

Order: P1 + P4 + P5 + P6 (a morning) -> P3 -> P8 -> P2 -> P7 (after part 1 I).

## 4. Tests
- pytest: `committed_v` project leg = raised OI remainder only (M310 case reproduces 0 at BRW-BB after the migration; MSK11B = 26 at BRW-BB); unclassified folds into retail; cover-sources hides PO for project rows; `po_confirm` links the sizing rows first; sidecar endpoints honour `rec_ids`.
- vitest: manual plan submits with no warehouse; no Unclassified column ever; history header one badge; decision cell has no advice line; sidecar hooks pass the page's ids.
- agent-browser on :3060: manual plan with empty warehouses; M310-CR-PJ row after P3; confirm a plan-generated PO and see the OI row linked and the PO Allocated to panel.

## 4b. Order back (captain's ruling on Link SPO)
- "Only for order back, we link to SPO allocations." A normal ORDER row is a new purchase and links to PO lines only. An ORDER BACK row is a shortfall against something already shipped or ordered, and may link to `spo_allocations` as well as PO lines.
- Model: `order_inquiry_rows.verb` gains `ORDER_BACK` (vocabulary: ORDER | ORDER_BACK | ...). Set by CS on the board (Amend: "Order back", optional cited document, which pre-fills the link) or by the Order Inquiry Form upload when the delivery-date cell reads ORDER BACK. `committed_v` treats ORDER_BACK exactly as ORDER (it is still demand until linked).
- Auto-link: ORDER rows walk PO lines; ORDER_BACK rows walk SPO allocations first (the cited document first if one is named), then PO lines. Same tiers, same cascade.
- Worklist: Verb filter gains Order back; the Linked to column shows SPO links only on such rows.

## 5. Questions (captain)
- **QP1** RULED: refuse the SO import until every order has a class. P4 becomes: validation error per unclassified order (test verdict names them), `committed_v` keeps no unclassified leg after the existing NULLs are classified by a one-time re-import; column removed.
- **QP2** RULED: keep "Use PO" for retail rows.
- **QP3** RULED: acceptable for UAT; no backfill. Sheet-origin orders wait for CS on the board.
