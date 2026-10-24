# PLAN-BATCH-COUNT-DISPLAY: Confirm and Saved count decisions only; the AutoCount change is one note

Status: Build (small fix track, size S: FE only, no migration, no auth/RBAC change)
UAC: `batch-count-display-21oct-acceptance-criteria.md` (alongside)
Follows: `PLAN-batch-held-cancel-21oct.md` (#1817). Owner ruling 21 Oct 2026 ~16:15 MYT.

## Ruling
Confirm (N) and Saved (N) count ONLY decisions someone made: user decisions and AutoCount Cancel
SO drafts. Lines a pending AutoCount change retires are NOT counted (SO394881: Confirm (12) /
Saved (12), not 22). The AutoCount change is shown as ONE separate plain note on the board and in
the Simulate / Confirm results, e.g. "Also applies the AutoCount change from 24 Sep: 10 old lines
(SRTWCX8840-S-RL) are retired": date, count and item codes from the batch. General for every SO
with a pending change.

## Design (file:line at 7622955d11)
FB = `_shared/lib/fulfilmentBoard.ts`, FBP = `fulfilment-planning/components/FulfilmentBoardPanel.tsx`.

1. FB `countsInPress`: role `cancelled` (a book-cancelled line the batch retires) is no longer
   counted. FB `pressPostsContribution`: back to main (the `cancelled` role #1817 added goes), so
   Saved is decisions only. The press still admits and posts such an order with its `batch_id`
   (#1817 crew item 3 stays: FBP `wantedOrders` + `retiresBookCancelled`).
2. FB new `autocountChangeNotes(contributions, excludeKeys?)`: per sales order, the lines the
   pending change retires (role `cancelled`): count and distinct item codes. FB new
   `autocountChangeSentence(...)`: the one sentence, in board / simulated / confirmed wording,
   "Also ..." when the press carries decisions for that order too.
3. FBP board: one notice block above the board listing one sentence per SO with a pending change
   (SO number prefixed only when more than one SO has one). Date = that SO's batch `created_at`
   (`bySoNumber`, FBP:526); none loaded -> "the pending AutoCount change".
4. FBP results: an order whose press applied the change reads its own sentence without the
   "applied the AutoCount change;" prefix, and the retired lines show as that one note (built from
   `lines_retired`), replacing the per-line "Retired by the AutoCount change: line ..." list. An
   order whose press ONLY applied the change reads the note as its sentence.
5. Button (pending crew answer, recommendation (a)): enabled when a pending change would be
   applied even at Confirm (0), so a change-only order is never stuck.

Architecture: one predicate (`pressRoleFor`) still classifies each line; the count, Saved, the
dialog and the note all read it, so the note's lines are exactly the role `cancelled` lines the
count leaves out. No server change: `lines_retired` and `planning_change_applied` already ship.

## Tests (red first)
- FB lib: SO394881 shape -> toConfirm 12, Saved 12; notes -> one entry, 10 lines, codes.
- FBP panel: Confirm (12); board note text; Confirm results: "SO394881: 12 lines transferred to
  Cancel SO" + the note; change-only order: button enabled, note "Applies ...".
- Simulate: "SO394881: would transfer 12 lines to Cancel SO" + "Would also apply ..." note.
