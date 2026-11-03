# PLAN: Dealer order lines at a project bin are plannable

**Status:** Plan. Track M (rule change in `planning_predicate.py`, no migration expected). Behaviour card filed as a crew ask before code.

## Journey

Dealer CS opens Fulfilment Planning on a Dealer sales order (prod SO428978, SRTUB206) whose line sits at project bin BRW-BB, already delivered from BRW-BB, and decides Borrow / Buy / order back on it. Today the board says "Outside fulfilment planning: BRW-BB is outside fulfilment planning", which blames the bin while the real cause is the order's class.

## Owner ruling (3 Nov 2026, ~10:15 MYT)

"I prefer to loosen the rule, project bin at dealer location is allowed, cause this one already delivered using BRW-BB, now need to order back."

## Rule change

`outside_fulfilment_planning` (`app/services/scm/planning_predicate.py`) drops the clause that refuses a retail/other order's line at ANY project bin. What stays: consignment exemption, dealer-segment exemption, a project bin that is active with `fulfilment_planning` OFF still refused, inactive bins unchanged. The refusal message names the real reason.

(Details filled in after the behaviour card is answered.)
