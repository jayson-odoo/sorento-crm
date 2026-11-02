# PLAN: CONFIRM-PREVIEW-STALE

Status: in review, PR #2091 (small fix track: no migration, no auth/RBAC change). Items 1-3 here;
item 4 is a stacked follow-up PR (crew ruling, 2 Nov).

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
