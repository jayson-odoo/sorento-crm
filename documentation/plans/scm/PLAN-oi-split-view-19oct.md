# PLAN: split follow-ups after #1749 (OI-SPLIT-VIEW)

Status: Plan. Behaviour card being drafted (crew ask), then a Lavish mock of the SO and OI Lines
tabs on SO417636; build only after the owner OKs both. Track: M (new rule on the board, UI on two
existing screens; no migration expected). Lead pattern: tester red tests, one coder, reviewer,
browser pass 1280/375 on the crew test copy.

Card: `oi-split-view-behaviour-card.md` (alongside, after discovery). UAC:
`oi-split-view-19oct-acceptance-criteria.md` (after the card is answered). Mock:
`documentation/mockups/OI-SPLIT-VIEW/index.html`.

## Journey

Owner 19 Oct ~20:30 MYT, after OKing #1749: "you have a follow up PR to make the split delivery at
this level [planning board] and it should be based on those that are saved only, not all the
lines, and I need this split detail visible at the sales order level at the line meaning I can
visualize the split from the sales order perspective, as well as the OI perspective at line level".

1. Planning board: after a plan is confirmed, a saved split-only edit (qty or date changed on the
   split sheet and Saved) shows in "Confirm (N)" and can be confirmed, so the change reaches
   purchasing (OI rows, email, Excel). Count only saved split edits that differ from the last
   applied plan. One function for engine, email and Excel; no CANCEL from splits (#1749 AC-G15
   gap, step 16 of laneboard/scripts/1749.md).
2. Sales Order page > Lines tab: each SO line shows its split detail.
3. Order Inquiry page > Lines tab: each OI line shows its split detail at line level.

## Steps

1. Discovery with file:line (board count, Confirm path, SO and OI Lines tabs, split read API).
2. Behaviour card as ONE crew ask.
3. Lavish mock on SO417636 (business data only, masked in the committed copy).
4. After owner OK: UAC, tester red tests, coder, reviewer, browser pass, hand-test script.

## Discovery (summary; full citations in the card)

- Board count is FE only: `confirmSummaryFor` (`_shared/lib/fulfilmentBoard.ts:861`) over board
  contributions; it never reads splits, so a split-only edit counts 0.
- Confirm applies only the lines the FE posts (`fulfilment_planning.py:1447`, `:446`). AC-G15's
  "edited applied plan" compare lives inside `_later_change_lines`
  (`project_order_inquiry_service.py:6028-6040`) and needs a pending AutoCount change on the line.
- Applied plan stamp: `split_plan_key` (`project_order_inquiry_service.py:237`) on the decision
  snapshot; newest per line read by `_recorded_split_plans` (`project_line_split_service.py:1021`).
