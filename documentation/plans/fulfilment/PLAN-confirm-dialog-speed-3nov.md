# PLAN: CONFIRM-DIALOG-SPEED

Status: in review, PR 1 #2128. Track: standard (the diff passes ~300 lines, mostly tests; no
migration, no auth/RBAC change). PR 2 (`_oi_placements` and the confirm-all hot spots crew profiles) follows from main
after PR 1 merges. UAC: `confirm-dialog-speed-3nov-acceptance-criteria.md`.

Owner report (3 Nov 13:15): Fulfilment Planning -> Confirm SO423361 sits on the Review split
skeleton for a very long time on prod. Prod request log (3 Nov 12:50-13:32 MYT): POST
`confirm-all` 36-46 s, GET `board` 6-8 s typical, 20 s worst. New since #2091
(CONFIRM-PREVIEW-STALE): openGuide re-read the whole board, then the Review split waited on the
confirm-all dry run as well, in series.

## PR 1: the dialog stops waiting

1. The Review split waits for the board re-read and the order's split read only, never for the
   email dry run. Next is usable while the dry run is out.
2. The email dry run starts as the guide opens, on the decisions the tab holds, beside the board
   re-read. Runs are keyed by the body they send plus a counter every save on a guide page bumps
   (the body carries no split rows). A read that leaves both unchanged keeps the run out.
3. The Confirm step waits for the dry run under "Preparing email preview..."; the run still out
   when Next is pressed finishes there. A failed dry run shows its own line and Retry and holds
   Confirm only; the sheet (and any unsaved edit) stays.
4. Opening Confirm joins a board read already in flight instead of cancelling and resending it.

Not done, on evidence: re-reading only the opened SO. The board is the selection itself and its
cells pile several orders together, so one order's read cannot be merged into it safely; PR 2
makes the read itself faster instead.

Trade accepted for owner confirmation: on a multi-order Confirm, paging on before a page's dry
run lands cancels that run (at most one in flight, #2116), so that page was shown in the board's
words. Confirm waits only for the last page's run; the press still runs its own dry run.

## PR 2: confirm-all and `_oi_placements`

`_oi_placements` starts from the SO lines' own order-inquiry placements and reads only the SPO
rows those name, by id, instead of one join the planner nested-looped over 1.45M
`spo_allocations` rows. Results identical: an equivalence test keeps the old statement as the
oracle. Further confirm-all hot spots per crew's profile.
