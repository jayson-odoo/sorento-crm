# PLAN: OI line follows the SO line's product change from AutoCount (OI-PRODUCT-FOLLOW)

Status: Build (owner answered the card 2 Oct; rulings R1-R6 below). S1 built.
Track: feature (M, carries one migration, so not the small fix track). Cloud lane.
Lane: OI-PRODUCT-FOLLOW, branch `claude/oi-product-sync-6uoz28`, PR #1442.
Domain: scm (ESB sales order ingest, order inquiry rows, planning board apply).
Prod SQL: `oi-product-follow-prod-readonly.sql` (read-only) and
`oi-product-follow-correction-PROPOSED.sql` (owner approves, crew never runs it), alongside.

## Problem (owner, 2 Oct, prod)

SO423414 (TEXON CONSTRUCTION) had its line products changed in AutoCount (same line refs),
but OI-2609-0776 still shows the old products (MWCX7604-S-RL-NEW / MWCY7604 / MWC-SC04-QQ
vs the SO's MWCX7604-SH-S10 / MWCY7604-SH / MWC7604-SC-SH).

Owner rule: when an SO line's product changes, the linked OI line switches to the new
product exactly like quantity and delivery date already do, keeping the old value visible
("was X").

## Measured (origin/main 4f8e97c8, `sorento_crm_backend/`)

How a qty/date change reaches an OI row today (the flow to copy):

1. ESB push: `document_ingest_service._sync_lines` matches the line by `source_ref` and
   writes every column in place (1522-1523), `product_id` included.
2. `_sync_mirror_line` (1370-1392) copies `required_date` and `qty_ordered` to the mirror
   `projects.sales_order_lines` row. **Not `product_id`.** The manual SO edit path does
   move it (`scm/sales_order_service.py:1806-1815`), so the two writers disagree.
3. The planning hook (`api/v1/external/ingest.py:385-420`) diffs before/after by line id
   (`scm/outstanding_diff.py:236-260`); a swapped item code is ONE `product_changed` row
   (`:194-207`), gated on the order holding a decision or a live OI row
   (`planning_change_service.py:1097-1122`, `:2190`).
4. A planner applies the row on the board: `supply.confirm(settle_in_place_line_ids=...)`
   (`planning_change_service.py:4382`) -> `refresh_for_decision` ->
   `_settle_row_in_place` (`project_order_inquiry_service.py:1894-1910`), which writes
   `qty`, `delivery_date`, `previous_qty`, `previous_delivery_date`, flips an
   acknowledged row to `changed` and records the handover "was".
5. **`OrderInquiryRow.item_code` has no writer after creation** (only the raise at
   `:1477` / `:1590` / `:4121`). The apply entry already carries the NEW code
   (`project_supply_service.py:6853`, `_carried_lines` patches identity at `:5318-5328`),
   and `refresh_for_decision` finds the row by `so_line_id` + verb (`:1012-1019`), so the
   row is restated on qty/date and keeps the old product. That is the SO423414 symptom.
6. Side effect of (2): `auto_place_products` reads `entry["line"].product_id`
   (`project_supply_service.py:6955-6961`), the stale mirror product.
7. There is no `previous_item_code`; the "was" UI reads `previous_qty` /
   `previous_delivery_date` (`_shared/lib/orderInquiryAck.ts:90-98`,
   `orderInquiryWorklistColumns.tsx` QtyCell 740-750, `orderInquiryLineFold.ts:279-289`).

## The owner's two "already works" claims, verified

**(1) A new SO line reaches the OI through the existing flow: ALREADY WORKS (via the board).**
ESB creates the core line (`document_ingest_service.py:1543-1553`), mirrors it when the
order is an adopted mirror (`:1589-1605`), and `build_batch` raises an `added` row for an
order that holds a decision or a live OI row (`planning_change_service.py:922-940`,
`:1097-1122`). The OI row is raised when a planner applies that row (CS raises), never
automatically. **WESERP10B on SO423414**: expected reason is that its `added` row is still
PENDING on the planning board (nobody applied it). Read-only Q3 confirms or refutes; if Q3
shows no `added` row at all, Q1 will show whether the line has no mirror (an authored
project order is not self-healed at `:1593-1603`).

**(2) An OI row whose SO line AutoCount cancelled shows cancelled: ALREADY WORKS for a
removed line, GAP for a zeroed line.**
- AutoCount line REMOVED from the push: the leftover sweep marks it `cancelled` because the
  mirror line references it (`document_ingest_service.py:1560-1574`), calls
  `flag_rows_for_cancelled_lines` (`:1578-1585`), and the OI reads `line_cancelled` off
  `SalesOrderLine.line_status` (`order_inquiry_worklist_service.py:482-484`) and shows
  "Line cancelled" (`orderInquiryLineFold.ts:256`, `OrderInquiryVerbPill.tsx:131`). Works.
- AutoCount line kept with qty set to 0: `_line_status` returns `open` for ordered 0
  (`document_ingest_service.py:1819-1825`), so nothing is cancelled and nothing is flagged;
  the OI row stays as it was until a planner applies the `cancelled` change row. The manual
  edit path DOES cancel a line zeroed on the transition (`scm/sales_order_service.py:1817-1828`).
- **M-FH14 138 on OI-2609-0776**: either (a) the zeroed-line gap above (Q1 shows
  `qty_ordered = 0`, `line_status = open`), or (b) the line IS `cancelled` and the row is
  waiting on purchasing's Confirm (ruling C1 of `PLAN-oi-cancelled-line-used-confirm.md`:
  a cancelled-line row goes to To confirm and the header sits Outstanding until confirmed),
  or (c) the row's `so_line_id` / mirror core link is NULL so no line status reaches it
  (Q2 `mirror_core_line` NULL). Q1 + Q2 tell which.

## Owner rulings (2 Oct, on the card)

- **R1 (Q1)** The OI line switches to the new product when CS clicks Confirm in fulfilment
  planning: the same apply moment as qty/date today.
- **R2 (Q2)** A row already linked to a PO/SPO line is NOT unlinked. The link follows
  AutoCount and flows through; the change is flagged with the EXISTING mechanism the
  qty/date change uses on linked rows (`ack_state` -> `changed`, `changed_at`,
  `_dispatch_changed_with_links`). No new unlink behaviour.
- **R3 (Q3)** Fix ALL rows already wrong on prod. Correction script for the owner:
  BEGIN, dry-run count first, default ROLLBACK, plus the read-only check. Crew never runs it.
- **R4 (email)** On Confirm the handover email to purchasing says
  "change item code to <new>" (was <old>), in the same style as the qty/date change lines.
- **R5 (Q4)** New SO lines: today's flow (they appear on Confirm in fulfilment planning).
  No change.
- **R6 (Q5)** A line set to qty 0 in AutoCount stays as today (cancel balance on confirm).
  No change; the qty>0->0 auto-cancel proposal is dropped (S4 removed).

## Design (per the rulings)

- **S1 mirror follows product (ingest).** `_sync_mirror_line` also copies `product_id`
  when the push carries it, same as the manual edit path. Fixes item 6 too.
- **S2 OI row follows product (apply).** Migration: `order_inquiry_rows.previous_item_code`
  (nullable). `_settle_row_in_place`: when the entry's `item_code` differs from the row's,
  the row takes the new code, keeps the old in `previous_item_code`, notes "Was X", counts
  as a real change (acknowledged -> `changed`, `changed_at`, `_dispatch_changed_with_links`,
  handover "was"). Links stay exactly as they are (R2).
- **S3 UI.** Item cell on the worklist and the OI Lines tab: new code, muted "was X" under
  it, same look as the qty/date "was". History dialog "Was X." prefix.
- **S4 email (R4)** The handover settled line carries `was.item_code`; the template prints
  "change item code to <new> (was <old>)" beside the qty/date change lines.

## Test list (red first)

- ESB re-push with a swapped product moves the mirror `product_id` (S1).
- Apply of a `product_changed` row: OI row `item_code` = new, `previous_item_code` = old,
  qty/date untouched when unchanged, acknowledged row -> `changed`.
- Same with a PO link on the old product: link removed, stamp written, no link on the
  new product, PO line untouched.
- Idempotent re-push / re-apply: no second "was", `previous_item_code` not overwritten
  with the new code.
- Worklist + header-lines payload carry `previous_item_code`; FE Item cell renders "was X"
  (vitest).
- (S4) push with qty 0 on an open line -> `cancelled` + flag; already-0 line resent -> no
  change.
