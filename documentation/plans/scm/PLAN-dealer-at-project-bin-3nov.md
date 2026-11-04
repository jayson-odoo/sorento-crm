# PLAN: Dealer order lines at a project bin are plannable

**Status:** Built, in review. Track M (rule change in `planning_predicate.py`, no migration, no auth change). PR #2122, branch `claude/dealer-project-bin-planning-duugql`, crew lane DEALER-AT-PROJECT-BIN.

## Journey

Dealer CS opens Fulfilment Planning on a Dealer sales order (prod SO428978, SRTUB206) whose line sits at project bin BRW-BB, already delivered from BRW-BB, and decides Borrow / Buy / order back on it. Before: the board said "Outside fulfilment planning: BRW-BB is outside fulfilment planning", which blamed the bin while the real cause was the order's class.

## Owner ruling (3 Nov 2026, ~10:15 MYT)

"I prefer to loosen the rule, project bin at dealer location is allowed, cause this one already delivered using BRW-BB, now need to order back."

## Card answers (crew + owner, 3 Nov)

- Q1 (a): the order inquiry routes by the SO class (DEALER-OI-ROUTE, 1 Nov, editable in Automation). No code change.
- Q2 (a): the line walks the project bin's own ladder (own pile, group, site pool under the dealer share cap, donors), exactly like a project line at that bin. No code change.
- Q3 (b), owner: "I don't want so complicated, I want to just allow". A Dealer/Other order with a line at an active bin IN fulfilment planning is admitted, no date window.

## Change

`app/services/scm/planning_predicate.py`:

1. `outside_fulfilment_planning`: the clause refusing a retail/other order's line at ANY project bin is gone. The verdict is now the same for every class: an active project bin with `fulfilment_planning` OFF. Consignment and dealer-segment exemptions unchanged; inactive bins unchanged.
2. `admitted_to_planning`: the EXISTS that admitted a retail/other order on a line at an active dealer-segment bin now also admits on a line at an active bin with `fulfilment_planning` ON. Board, line drafts, adoption, SO list and plannable counts all read this one clause.
3. `why_not_admitted`: names both ways in.

Message: with the class clause gone the verdict only fires for a bin whose planning switch is off, so the existing sentence "BRW-SMC is outside fulfilment planning, so this line cannot be decided here" (`supplyVocabulary.ts`) now names the real reason. No frontend change.

## Unchanged on purpose

Consignment rules, dealer-bin rules, planning-OFF project bins refused and not admitting, inactive bins not admitting, `adopt_for_migration` and the OI import project-only, an unfiltered list call returns project orders only.

## Changed on purpose, disclosed

- A Dealer order line at an INACTIVE project bin (order admitted through another line) no longer reads "Outside fulfilment planning"; it reads exactly as a project line at that bin always has (the flag verdict never named a retired bin). Pinned by `test_an_inactive_project_bin_reads_the_same_for_every_class`.
- Any active bin with planning ON admits a Dealer order, an HQ project reserve flagged ON included. That is the owner's Q3 (b). The prod-copy count of newly admitted orders was not measured (cloud sandbox, no prod copy).

## Tests

`tests/scm/test_dealer_at_project_bin.py` (new, red on main), `tests/scm/test_retail_fulfilment_planning.py` (R2 / R4 removed with a pointer, two reason tests moved onto a planning-OFF bin).
