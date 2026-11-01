# UAC: DEALER-PLANNING PR 2, retail orders in Fulfilment Planning

Roles only, never staff names, in code, tests, docs or seeds. Owner answers: Q1 (a), Q2 (a), Q3 (a), Q5 (a). Reorder-run demand counting and `scm.committed_v` do NOT change.

## Admission
- R1 An open order of class `retail` or `other` with at least one line at an active dealer-segment location is listed, adopts with no project, opens on the board, takes line drafts, confirms and raises its OI. 'other' counts as retail (`demand_class.planning_class`).
- R2 A retail order with no line at a dealer-segment location stays out, as today.
- R3 An order with no class stays off the board, and the reason given is true: not "Every line is cancelled, fully returned" (`FulfilmentBoardPanel.tsx:3350-3353`).
- R4 On an admitted order, a retail line at a project location reads "Outside fulfilment planning" and cannot be decided, even at a location in planning.
- R5 Project-class orders are admitted exactly as today. `adopt_for_migration` and the OI import stay project only.

## Finding orders
- R6 The Fulfilment Planning list takes a multi-select `demand_class` filter, default Project, so a call with no filter returns what it returns today. Its row states the class. The Sales Orders list's existing Type filter and Plan selected work for retail. The sales order detail page offers Plan for an admitted retail order and not for an order that cannot be planned.

## Own location
- R7 A line at its own pool does not net its own demand against that pool; every other line's demand there stays netted. Same answer on its sheet, on the board alone, and on the board with other lines of the product.
- R8 What goes back is what the pool's book counted: a closed, non-transferable or covered line, or a line at a retired pool, adds nothing. Part delivered adds back what it still owes. Another line never reads this line's add-back.
- R9 A retail line at its own dealer location has no dealer share held back: 7 on hand, 5 ordered, nobody else: Reserve 5. 10 on hand, 10 ordered: Reserve 10. A project-class line at BRW keeps the share: 10 on hand, 10 ordered: Reserve 5 + Buy 5. Other locations keep the share for both classes.
- R10 Pools read one running net, spent as drawn, in the walk and at confirm. Confirming the engine's own proposal comes up short by nothing: 10 here, 40 at another pool, line of 30; 10 here, 30 and 30 elsewhere, line of 40; 0 here, 30 and 30 elsewhere, line of 50; two dates at one pool. A project line's sheet is unchanged, and on the board it changes only for a real draw.
- R11 A Reserve cannot take stock the book owes elsewhere or has reserved: 10 on hand, 50 owed to another order, Reserve 10: short 10. 10 on hand, 8 reserved: short 8. Two orders pressed separately cannot both hold the same 10.
- R12 The stock pop-up on a line at a pool states figures that agree with the suggestion, for both classes: today it shows Available for Project 30 against Site pool 15 with nothing explaining it.

## Priority and display
- R13 A retail OI row competes for a scarce PO line at its real class weight, not project (`project_order_inquiry_service.py:13930`, `priority.py:110-117`).
- R14 A retail order's internal note does not print as a project name (`project_so_reconciliation_service.py:219-226`, `project_fulfilment_board_service.py:401-424`).

## Loading Plan (`container_request_service.py`, the Lines tab)
- R15 A confirmed retail line stays on the Loading Plan once, in the Retail column, less SPO links: Buy 10 with 0 on hand: Retail 10, ask 10. Reserve 10 with 10 on hand: Retail 10, ask 0. 4 linked to an SPO: Retail 6. Its product keeps its demand row. `so_count` counts an order once. Undecided retail and every project figure are unchanged, and `build`'s invariant (`sum(qty)` per product equals `open_so_need`) holds.

## Access
- R16 An additive, idempotent migration gives the Customer Service role `projects.projects.view`, `projects.projects.edit` and `scm.dashboard.view`. A role missing on a database is not an error. No other role changes. One alembic head.
