# PLAN: OI line follows the SO line's product change from AutoCount (OI-PRODUCT-FOLLOW)

Status: Plan (behaviour card pending owner answers). Track: feature (M), cloud lane.
Lane: OI-PRODUCT-FOLLOW, branch `claude/oi-product-sync-6uoz28`
Domain: scm (order inquiry rows, ESB sales order ingest)

## Problem (owner, 2 Oct, prod)

SO423414 (TEXON CONSTRUCTION) had its line products changed in AutoCount (same line refs),
but OI-2609-0776 still shows the old products (MWCX7604-S-RL-NEW / MWCY7604 / MWC-SC04-QQ
vs the SO's MWCX7604-SH-S10 / MWCY7604-SH / MWC7604-SC-SH).

Owner rule: when an SO line's product changes, the linked OI line switches to the new
product exactly like quantity and delivery date already do, keeping the old value visible
("was X").

(Measured facts, design and test list follow in the next commit.)
