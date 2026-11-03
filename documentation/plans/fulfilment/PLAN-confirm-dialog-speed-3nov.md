# PLAN: CONFIRM-DIALOG-SPEED

Status: in progress, PR 1 (dialog stops waiting). Track: small fix (no migration, no auth/RBAC
change). PR 2 (`_oi_placements` query) follows from main after PR 1 merges.
UAC: `confirm-dialog-speed-3nov-acceptance-criteria.md`.

Owner report (3 Nov 13:15): Fulfilment Planning -> Confirm SO423361 sits on the Review split
skeleton for a very long time on prod. New since #2091 (CONFIRM-PREVIEW-STALE), which made
openGuide re-read the WHOLE board and then wait on the confirm-all dry run before step 1 renders.

## PR 1: the dialog stops waiting

1. Opening Confirm re-reads only the opened SO's board slice, not the whole board. #2091's intent
   is kept: the preview never shows data older than the last board save.
2. Step 1 (Review split) renders once that SO's own data is fresh. It does not wait on the
   confirm-all dry run (email wording).
3. The dry run loads in the background; step 2 (Confirm) shows its own loading state until it is
   ready. Email = preview = attachment still tally (same dry run feeds all three).

## PR 2: `_oi_placements`

Start from the SO's own order-inquiry rows and join the SPO by id instead of filtering the
1.45M-row `spo_allocations` scan by 1,331 refs. Results identical: equivalence test keeps the old
implementation as the oracle.
