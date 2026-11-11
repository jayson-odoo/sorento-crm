# PLAN: Stock Debt frozen SO qty, live linkage / reserve (STOCKDEBT-LIVE-ACTIONS)

Status: Plan (small fix track pending measurement). Part 1 building; Part 2 (Change PO) waits on owner card answers.

## Owner ruling (11 Nov 2026)
Frozen in a snapshot: SO lines in scope, their quantities, dates, location, customer/project, and totals/Short
derived from those quantities. Live: PO linkage (Covered by / Assigned / Pinned / Short-by-cover), reserve
requests, OI grouping (30 Oct rule), Decision state, anything a Decide action changes.

## Frozen vs live table
(filled in after reading the code; copied into the PR body)
