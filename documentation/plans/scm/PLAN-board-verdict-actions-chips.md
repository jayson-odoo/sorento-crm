# PLAN: Fulfilment board - verdict actions in the row, document chip ladder, Was/Now lightbox

Status: implemented, reviewed, browser pass done, awaiting PR (22 Sep 2026). Track: normal lane, FE only, no migration.
UAC: `board-verdict-actions-chips-acceptance-criteria.md`.
Branch `feat/board-verdict-actions-chips`, worktree `sorento_crm-board-verdict-actions`.

## Owner findings (22 Sep 2026, prod SO402757)

1. Product cell shows `received` but nothing when the line has a PO, an SPO or only an OI.
2. `Change proposed` pill has no accept / reject in the row.
3. Reject needs a reason popup over the X, same fields as the panel footer.
4. Verdict column cannot be resized.
5. "What changed" lightbox is plain arrow text; the Order Inquiries Was/Now box reads better.

## Today (origin/main 2280975f9)

- `boardOrderInquiryWord` (`_shared/lib/supplyVocabulary.ts:870`) returns only `received` /
  `used` / null. `order_inquiry.documents[{document, kind: po|spo, received}]`,
  `inquiry_no` and `state` are on every contribution already; nothing renders them.
- Pre-mark = session draft `{verdict:'approved', preMarked:true}` (`FulfilmentBoardPanel`
  ~line 557). Verdict cell (`FulfilmentBoardListView.tsx:558`) shows the tick only when
  `canQuickSave` (no draft entry) and withholds Undo on a pre-mark (`isPreMarkOnly`), so a
  Change proposed row has no action. Grid twin at `BoardCellBreakdownDialog.tsx:~880` has
  Undo only.
- Reject with reason + `suspected_system_issue` exists only in `BoardLineDecisionPanel`
  (`reject()` ~line 457, footer ~line 950).
- `enableResizing: false` on the Verdict column, size 190 (list), 140 (grid).
- `BoardChangeTable.tsx`: `BoardChangeSummary` (arrow lines, board lightbox) and
  `BoardChangeWasNowTable` (amber table, imported by `OrderInquiryQtyAnnotationDialog`) live
  in the same file. The 13 Sep move off the table was for the CELL, not the dialog.

## Rulings

- R1 (default, 22 Sep): chip is a word (`OI` / `PO` / `SPO`), number in the tooltip.
- R2 (default): Accept on Change proposed = `suggestedDecisionFor`, what Confirm writes.
- R3 (default): Confirmed line gets Change decision only. Superseded 22 Sep 2026 by
  `PLAN-board-reject-on-confirmed-line.md` R3(b): a confirmed line now also shows Reject,
  which takes the line out of the confirmation and records the rejection.
- R4 (owner "go", 22 Sep): lane opens now off origin/main. The sibling lane
  `fix/board-options-collapsible-reject-feedback` (uncommitted, touches
  `BoardLineDecisionPanel` + `FulfilmentBoardPanel.decide` toast) is NOT touched here; this
  lane does not edit those two files. Whichever merges second rebases.

## Fix

One helper, one shared component, two views wired, one lightbox body swap.

1. `_shared/lib/supplyVocabulary.ts`: `boardOrderInquiryWord` returns
   `{ word: 'received'|'used'|'SPO'|'PO'|'OI', title: string } | null` per AC-A7. Both
   Product cells read it (grid dialog product cell too if it draws the word; if not, add the
   same Badge there).
2. New `fulfilment-planning/components/BoardVerdictActions.tsx`: props
   `{ contribution, decision, onDecide(decision|null) => Promise<boolean>|void, onChange() }`.
   Renders per AC-B1 to B10: Accept / Reject-popover / Change decision / Undo. Popover =
   `Popover` + `PopoverPortal` from `@/components/ui/popover`, `Textarea`, `Checkbox`, `Button`.
   `stopPropagation` on every click. Reject failure keeps popover open.
3. `FulfilmentBoardListView.tsx` verdict column: `<BoardDecisionPill/>` +
   `<BoardVerdictActions onChange={() => setExpanded(add key)} />`; `size: 240, minSize: 170`,
   drop `enableResizing: false`. Keep `accessorFn` sort.
4. `BoardCellBreakdownDialog.tsx` verdict column: same, `size: 200`; `onChange` expands the
   row through the dialog's own expansion state.
5. `BoardChangeTable.tsx`: `BoardChangeSummary` renders `<BoardChangeWasNowTable annotation
   omitHeader />` in place of the `fields` list; rest of the body unchanged. Remove the now
   unused "kept for the ORDER INQUIRIES worklist alone" comment.

Not touched: `FulfilmentBoardPanel.tsx`, `BoardLineDecisionPanel.tsx`, backend.

## Tests (vitest, tester writes first)

- `supplyVocabulary.test.ts`: AC-A1 to A7 (ladder, tooltip text, cancelled OI, empty).
- `BoardVerdictActions.test.tsx` (new): B1 to B10 (buttons per state, reject popover
  disabled-until-reason, submit body, failure keeps open, Escape, propagation, change
  decision callback).
- `FulfilmentBoardListView.test.tsx`: Change proposed row shows trio; Saved row shows Undo +
  pencil; pencil expands the row; Verdict column resizable (`enableResizing` not false).
- `BoardCellBreakdownDialog.test.tsx`: same trio on a Suggested row.
- `BoardChangeTable.suggestion.test.tsx`: lightbox renders the Was/Now table
  (`board-change-<rowId>` testid) + suggestion lines; OI dialog test untouched.

## Verification

Phase 3: reviewer once, browser pass via sidebar on the lane stack (slot :3080/:8080),
evidence per AC-E1. Then draft PR. NEVER merge without owner go.

## Addendum 22 Sep (owner: "why so many warning signs")

`changeIcons` (`FulfilmentBoardListView.tsx:211`) maps every annotation for the line to its
own icon, so two pending batch rows on one line = two icons in one column. Fix (AC-D5):
`changeIcons` groups the filtered annotations and renders ONE `BoardChangeTable` per column
carrying `annotations: BoardChangeAnnotation[]`; the lightbox body stacks a Was/Now table per
annotation, newest first. Same grouping in the grid dialog if it draws icons the same way
(check `BoardCellBreakdownDialog` / `FulfilmentBoardMatrix` callers of `BoardChangeTable`).
`BoardChangeTable` keeps a single-annotation call signature working (wrap in an array) so
other callers do not change.

## Addendum 22 Sep (owner: Undo after Save lands on Suggested, not Change proposed)

`decide(key, null)` (`FulfilmentBoardPanel.tsx` ~695) deletes the draft key; the seeding
effect (~546) is guarded by `preMarkedBatchIds` and never re-seeds. Fix (AC-B13): the
seeding effect also records the pre-marked keys in a ref (`preMarkedKeySet`); `decide()`
with `decision === null` writes `{ verdict: 'approved', preMarked: true }` over a key in that
set instead of deleting it (the server DELETE still runs; the catch-revert path is
unchanged). This is the ONE edit this lane makes to `FulfilmentBoardPanel.tsx`; the sibling
lane `fix/board-options-collapsible-reject-feedback` edits the toast line of the same
function, so whichever merges second resolves a small conflict there.

## Evidence run (22 Sep 2026)

agent-browser, headless, lane stack. Text log per `documentation/agents/browser-verification.md`:
an evidence run IS this log, and the folder keeps two screenshots only
(`evidence/board-verdict-actions-chips/AC-B1-B2-verdict-trio-suggested-and-change-proposed-1280.png`,
`AC-D1-D3-change-lightbox-375.png`, both under 200 KB; the other 16 were deleted before the PR).

**Route, by sidebar clicks from `/`** (never a deep URL, so nav config, `moduleKey` and
permission gating are exercised): Supply Chain > Project Demand > Fulfilment Planning >
search `SO402757` > Plan.

**Network seen on the run:** board `GET /api/v1/.../planning-board` 200; line draft
`PUT .../line-draft` 200 on Accept and on Save decision; line draft `DELETE .../line-draft`
204 on Undo and on Undo all; `PUT /api/v1/list-query/column-config/...` 200 after the Verdict
column was dragged. No 4xx or 5xx once AC-B14's skip landed (see below).

**Per AC:**

- A1, A4, A5, A6, A7, A8: PASS. A2 (`used`) and A3 (an SPO with an unreceived document) are
  unit-only, as SO402757 carries no redirected line and no unreceived SPO line to render.
- B1 to B11: PASS (trio on a Suggested and on a Change proposed line, reject popover with a
  typed reason, `Rejected` pill after submit, pencil expanding the row, same set in the grid
  dialog).
- B13: PASS. Accept then Undo returns line 1 to `Change proposed`, not `Suggested`.
- B14: FAIL on the run, PASS after fix round 4. The board-wide Undo all discarded every draft
  silently, and fired 17 DELETEs of which 16 answered 404 because the key was a bare pre-mark
  with nothing saved behind it. Now: pre-mark keys are skipped in the delete loop, and the
  success branch toasts `N line(s) undone`, counted over the lines that had a decision to
  discard.
- C1, C2: PASS. Default width 240, clamped at the 170 minimum when dragged narrower, and the
  cell stays one line at 375px.
- D1, D2, D3, D4, D5: PASS.
- D6: PASS on the table stacking. The per-block facts (product swap, where it went, lateness,
  moved transfer, one per change) are unit-only: no line on SO402757 carries two pending
  changes that each moved something different.

17 of 18 checks passed on the run; the one that did not is B14, fixed in round 4 and covered
by `FulfilmentBoardPanel.undo.test.tsx` (`AC-B14: toasts the lines it actually undid, and
never DELETEs a bare pre-mark`).
