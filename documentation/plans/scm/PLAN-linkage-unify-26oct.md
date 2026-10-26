# PLAN: one answer to "where are this SO line's goods now" (LINKAGE-UNIFY)

Status: SCOUT in progress, 26 Oct 2026 (report only, no product code). The fix that follows is
expected to be L (several screens, stock debt, chatbot). Lane LINKAGE-UNIFY, branch
`crew/linkage-unify`, base origin/main 263643ae36.

## 1. Why (owner, 26 Oct)

"This is the point of breaking, cause our calculation of linkage of PO SPO and SO is not unified."

Real case: OI-2609-0128 line 880, SRTSS4210, 486, placed on PO 202607-S0100 line 2. AutoCount
moved that PO line onto SPO-2026/09-0107 line 9 (BRW-BB, 486/486 received). The OI Lines tab
shows PO 202607-S0100, SPO "-", state "On PO/SPO"; the PO popup shows the same line on
SPO-2026/09-0107; Stock Debt (#1850) follows PO -> SPO a third way.

## 2. Inventory (every reader of the chain)

TODO (scout).

## 3. Divergence on dev data

TODO (scout).

## 4. Design: one function, one home module

TODO (scout).

## 5. Behaviour card (owner questions)

TODO (scout).

## 6. Slicing

TODO (scout).
