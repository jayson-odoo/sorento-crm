# PLAN: Target commission view + shareable commission statement (TARGET-COMMISSION-VIEW)

Status: Plan (card first: crew report --ask + Lavish mock). Track: standard (export surface, no migration expected).

Lane: TARGET-COMMISSION-VIEW. Coordinates with TARGET-INVOICED (#2162), which adds the Invoiced basis on the same screen.

## Journey
Owner opens Sales > Targets > TGT-000008 (A CRAFT IDEA SDN BHD 2026 quarterly). He wants to see the
total commission earned to date (Q1 3,681.10 + Q2 3,237.02 = 6,918.12), per period, and which
account it pays to, then send a statement to stakeholders to cross-check.

## Scope
1. Commission summary on the target (total to date, per period: target, achieved, %, tier hit, rate,
   commission, pays to).
2. Accounts tab: per account, sales + commission per period, clear labels, "Pays to" beside the
   commission.
3. Commission statement export per target and for many targets (Targets list multi-select), with
   the documents behind "Achieved" and the tier table. One computation shared with the screen.
4. Card: how "Achieved" is computed today, with file:line.

Details follow in the card and the mock.
