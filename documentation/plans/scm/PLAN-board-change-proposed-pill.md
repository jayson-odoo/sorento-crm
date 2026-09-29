# PLAN: A pre-marked changed line reads "Change proposed", not "Saved"

Status: in review (18 Sep 2026). Track: small fix.
Owner ruling 18 Sep 2026: the word is "Change proposed".
Superseded in part by owner ruling 25 Sep 2026 (issue #1245, `PLAN-esb-change-row-refresh.md`
S5): the pill stays as ruled here, but "the pre-mark still counts toward Confirm (N) exactly as
today" below no longer holds - Confirm now counts and posts only a SAVED verdict.

## Today

`FulfilmentBoardPanel` pre-marks, in React state only, every line a PENDING planning-change
batch names (`preMarkedKeys` -> `setDraft(next[key] = { verdict: 'approved' })`, "Nothing is
written here"). `BoardDecisionPill` reads `draftSource = decision ?? contribution.draft?.decision`
and prints "Saved"; the Verdict column shows the Undo arrow off `drafted = Boolean(draft[key])`.
So a confirmed line the book changed (SO421287 line 15, product SRT382-6 -> SRT382-6-DIY) reads
"Saved" with no "Saved by" popover. Its Undo does not 404 (`deleteLineDraft` has tolerated a
missing row since ba086aa6c) - it silently discards the pre-mark instead: the DELETE succeeds
against a row that was never written, the pill goes back to whatever it would have read with no
draft at all, and the line drops out of Confirm (N) with no error and nothing telling the
planner their "Undo" just threw away the board's own suggestion rather than anything they had
saved. The owner read the pill itself as an autosave.

## Fix

A pre-mark is distinguishable: it is in the session `draft` map but `contribution.draft` (the
server-saved draft) is null and the line is named by the open change batch. One rule at one
seam:

- `BoardDecisionPill`: new verdict `change_proposed`, label "Change proposed", own pill colour
  (amber outline, the change-hazard family), chosen when the session draft exists, the server
  draft (`contribution.draft`) is absent, and the line carries a pending change annotation
  (whatever `uncoverChangedLines` / `changedFieldsOf` already exposes on the contribution).
  A real saved draft on a changed line still reads "Saved".
- Verdict column (`FulfilmentBoardListView`) and the grid equivalent: no Undo arrow on a
  pre-mark (nothing to undo); the pre-mark still counts toward Confirm (N) exactly as today.
- `confirmSummaryFor` and the decision strip counts are unchanged (they count by draft entry,
  not by label). If the label lookup is a shared map, add the key there too.

No backend change.

## Tests (vitest)

- BoardDecisionPill: pre-mark on a changed line -> "Change proposed"; server-saved draft on a
  changed line -> "Saved"; pre-mark with `suspected_system_issue` on the frozen decision does not
  show the flag (unchanged behaviour, pin it).
- FulfilmentBoardListView: pre-marked row has no Undo button; saved row still has it.
- Existing pins that expected "Saved" on a pre-marked line are updated.
