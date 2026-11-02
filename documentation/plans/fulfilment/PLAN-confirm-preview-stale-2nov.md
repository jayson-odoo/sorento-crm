# PLAN: CONFIRM-PREVIEW-STALE

Status: in review, round 2, PR #2091. Track: standard (the diff is past the ~300 line small fix
limit; no migration, no auth/RBAC change). Items 1-3 here; item 4 is a stacked follow-up PR
(crew ruling, 2 Nov). UAC: `confirm-preview-stale-2nov-acceptance-criteria.md`.

Owner report (2 Nov 2026, Fulfilment Planning): a sales order whose lines are all delivered in
full, with a pending AutoCount change on one line (date 28/09 -> 02/11; suggestion Borrow 3 ->
Buy 3). The Confirm dialog's Review split showed DELIVERY DATE 28/09, NEW DATE blank, breakdown
"Delivered in full: nothing goes to purchasing", REMARK "ORDER BACK". After a board Save, Confirm
did not show the latest decision until a page refresh.

Owner rulings this lane honours: "popup = email = Excel" (26 and 28 Oct); "one bad line never
refuses an order"; "delivered or not doesn't affect our planning" (22 Sep, 12 Oct, 1 Nov); own-bin
borrow emails purchasing (2 Nov).

## Fix

1. Cache freshness: board Save refreshes the board; opening Confirm re-reads the board and split
   sheets and waits; a newer server decision is never silently overwritten by a stale tab.
2. Review sheet = email rows: delivered lines named by a pending change show NEW DATE and the
   change words; no "nothing goes" note.
3. Warning, never refusal: a saved decision that differs from the pending suggestion is flagged
   with Keep / Take suggestion.
4. Plain Confirm, delivered line with an order back goes to purchasing (remove the #1362 skip).

## #1362 skip provenance (item 4)

Not an explicit owner ruling: issue #1362 comment 5882662802 (29 Sep), "Third item". The owner's
words were only about not finding the line; the "confirm-all skips it" expectation was the
orchestrator's, written to stop a stale Buy on a fulfilled line refusing the whole order (R7
guard). Crew ruling (2 Nov): never refuse; a delivered line whose saved decision is a Borrow tells
purchasing its order back; a Buy on a delivered line keeps the skip. Built in its own stacked PR
with red tests that include the #1362 case.

## Outcome (items 1-3)

1. Freshness. A board Save still patches the cache only (D16 pins "invalidates nothing"). Opening
   Confirm re-reads the board and the review waits (`FulfilmentBoardPanel.openGuide`,
   `ConfirmGuideDialog` `refreshing`); split reads re-read on open and a page is loading until a
   read answered after open (`useLineSplitsReads(..., {fresh: true})`, `dataUpdatedAt`). A board
   read whose draft `saved_at` is later than the one this tab holds replaces the local decision
   and toasts ("... was saved again elsewhere"), `newerServerDraftKeys`.
2. Popup = email. `line_plans` keeps a pending change's Was -> Now on a delivered-in-full line
   (NEW DATE 02/11, change word); `LineSplitSheet` drops the "nothing goes to purchasing" note on a
   line a pending change names.
3. Warning. `suggestionMovedOf`: a saved decision (not the pre-mark) whose board words differ from
   the change annotation's Now decision shows "AutoCount moved this line: suggestion X, you keep Y"
   with Keep / Take suggestion (Take drops the draft back to the change's pre-mark). Next stays on.

Tests: `tests/scm/test_confirm_preview_delivered_change.py` (red first); vitest
`FulfilmentBoardPanel.confirmGuide.test.tsx` "CONFIRM-PREVIEW-STALE" (3 of 4 red first),
`ConfirmGuideDialog.moved.test.tsx`, `_shared/lib/confirmPreviewFresh.test.ts`.

## Round 2 (crew browser pass + reviewer, 2 Nov)

- A failed re-read on Confirm open (a slow board timing out) read as done, so the guide showed the
  tab's older decision with Next on, and Take suggestion from that view deleted the other tab's
  newer decision. Now the page shows a Retry; Next, Keep, Take suggestion and Confirm stay off
  until a read succeeds.
- The server refuses a draft save or Undo based on an older decision: PUT body / DELETE query
  `based_on_saved_at`; a stored draft saved after it answers 409 `board_line_draft_newer`
  (absent: last writer wins). The board re-reads on that 409.
- The moved warning compares compositions by kind and qty (`partsBreakdown`), never words (an
  incoming share read "from BRW" on one side only); a bare approval reads the proposal.
- `saved_at` bookkeeping follows every server draft the tab adopts; Undo and a covered line drop it.
- `line_plans`: a line AutoCount CLOSED because it was delivered in full is not CANCEL ALL; it reads
  its change words (every delivered line on the 20 Oct copy is closed).
- Hand test: the board is under Supply Chain > Project Demand > Fulfilment Planning in the staff
  sidebar (`config/menu.config.tsx:390-396`); the Project Sales entry exists only in the compact
  menu (`:2260`). Not a bug.

## Round 3 (crew final pass at 95e55739, 2 Nov): REMARK from the email itself

Captured final Confirm, run through the real confirm and rendered with the live template: every
column matched except REMARK. Saved Buy 25 read "ORDER" in the popup, "DELAY" in the email; Reserve
5 + Buy 20 read "CHANGED: ORDER 25 -> USE BRW-BB 5 & ORDER 20" against "DELAY, CHANGED: ...". The
popup printed the board's `saved_remark` (`saved_draft_remark`), a second copy of the rule that
does not see the date move or the rows' take-backs; the email builds REMARK in `_queue_saved_line`
during the write.

Fix, one source: the confirm dry run (`confirm-all` with `preview: true`) returns per order
`email_lines`, read off the handover queue this write filled, through `_build_handover_context`
(the builder the real send uses), before the rollback (`ProjectSupplyService._preview_email_lines`).
The guide runs that dry run once the board read is fresh (and again when the board or a decision
changes while it is open) and prints each line's email REMARK; a line the email does not tell reads
no remark; an order the dry run did not preview (not adopted, refused) keeps the board's words. The
review waits for it; a failed dry run shows the same Retry. Tests: BE red-first, both crew cases
equal the email the real press dispatches; vitest the page prints the dry run's words.
