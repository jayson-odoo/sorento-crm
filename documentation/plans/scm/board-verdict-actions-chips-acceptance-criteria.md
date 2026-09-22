# UAC: Fulfilment board - verdict actions in the row, document chip ladder, Was/Now lightbox

Plan: `PLAN-board-verdict-actions-chips.md`. Owner findings 22 Sep 2026 on prod SO402757.
FE only. No backend change, no migration.

Fixtures: `BoardContribution` rows built the way `FulfilmentBoardListView.test.tsx` and
`BoardCellBreakdownDialog.test.tsx` already build them. "Both views" below = the list view
(`FulfilmentBoardListView`) AND the cell breakdown dialog's contributing-lines table
(`BoardCellBreakdownDialog`).

## A. Product chip ladder

- **AC-A1** Given a line whose `order_inquiry.documents` are all `received: true`, When the
  Product cell renders, Then the chip reads `received` (unchanged).
- **AC-A2** Given `order_inquiry.redirected: true`, Then the chip reads `used` (unchanged,
  wins over A1 and A3 to A5).
- **AC-A3** Given `order_inquiry.documents` holds at least one `kind: 'spo'` document and the
  line is neither A1 nor A2, Then the chip reads `SPO`, and the chip's `title` is the SPO
  number(s) joined by `, `.
- **AC-A4** Given documents hold only `kind: 'po'` (none received, none redirected), Then the
  chip reads `PO`, `title` = PO number(s).
- **AC-A5** Given `order_inquiry` is present with `documents` empty and `state` not
  `cancelled`, Then the chip reads `OI`, `title` = `order_inquiry.inquiry_no` (or
  `Unnumbered inquiry`).
- **AC-A6** Given no `order_inquiry`, or `state === 'cancelled'` with no documents, Then no
  chip renders.
- **AC-A7** Exactly ONE chip per line, most advanced state wins, in this order:
  `used` > `received` > `SPO` > `PO` > `OI` (corrected 22 Sep after the coder's report:
  AC-RL-10 already ships `used` over `received`, since `used` means the received document
  was redirected off this line; AC-A2 "wins over A3 to A5" stands). Rule lives in ONE helper
  (`boardOrderInquiryWord` in `_shared/lib/supplyVocabulary.ts`, return type widened) and both
  views read it.
- **AC-A8** The chip is the same `Badge size="sm" appearance="light" variant="secondary"` the
  Product cell already draws; the cell stays one line tall at 375px and 1280px (product code
  truncates, chip does not).

## B. Verdict cell actions

Actionable line = `!covered && !unplannable && !cancelled`.

- **AC-B1** Given an actionable line with no session draft (verdict `Suggested`), Then the
  Verdict cell shows the pill and three icon buttons: Accept (`Check`, aria-label
  `Save <SO> line <n> as suggested`), Reject (`X`, aria-label `Reject <SO> line <n>`),
  Change decision (`Pencil`, aria-label `Change decision for <SO> line <n>`).
- **AC-B2** Given an actionable line whose session draft is a bare pre-mark (`preMarked` and
  no `contribution.draft`, verdict `Change proposed`), Then the same three buttons show.
  Accept calls `onDecide(key, suggestedDecisionFor(contribution))`. (Ruling R2: accept =
  the book's proposal as Confirm would write it.)
- **AC-B3** Given an actionable line with a real draft (verdict `Saved`, `Rejected` or
  `Suggestion changed`), Then the cell shows the pill, Undo (unchanged) and Change decision.
  No Accept, no Reject.
- **AC-B4** Given a covered line (verdict `Confirmed`), Then the cell shows the pill and
  Change decision only. (Ruling R3.)
- **AC-B5** Given a cancelled or unplannable line, Then the cell shows the pill / "Needs a
  location" text only. No buttons.
- **AC-B6** Accept click: `onDecide(key, suggestedDecisionFor(contribution))`, event does not
  propagate to the row (row does not expand).
- **AC-B7** Reject click opens a `Popover` (portal, `align="end"`) anchored on the X button,
  containing: label `Why this differs`, a required `Textarea` (placeholder `In your own
  words`), a `Checkbox` `This might be a system problem, flag it for investigation`, and a
  `Reject` button. The Reject button is disabled while the textarea is blank (same rule as
  `BoardLineDecisionPanel`, title `Say why this line is being refused first.`).
- **AC-B8** Popover Reject click calls
  `onDecide(key, { verdict: 'rejected', reason: <trimmed>, suspected_system_issue: <bool> })`
  and closes the popover. If `onDecide` resolves `false`, the popover stays open and the
  typed reason is kept.
- **AC-B9** Escape or outside click closes the popover without calling `onDecide`. Reopening
  starts blank. Clicks inside the popover do not expand the row.
- **AC-B10** Change decision click expands that row (the same `expanded` state
  `useDecisionRowExpansion` owns; in the grid dialog, the same expansion the row click
  triggers) and does not toggle it closed when already open. Event does not propagate.
- **AC-B11** Both views carry the identical rules B1 to B10; the buttons are one shared
  component (`BoardVerdictActions`, new file beside `BoardDecisionPill.tsx`) so the two
  cannot drift.
- **AC-B12** Bulk row selection (`enableRowSelection` off `canQuickSave`) and the toolbar
  bulk Save are unchanged.

## C. Verdict column

- **AC-C1** The Verdict column is resizable in both views (`enableResizing` no longer false;
  `minSize` 170).
- **AC-C2** Default `size` 240 in the list view, 200 in the grid dialog; the pill truncates
  before the buttons wrap.
- **AC-C3** Verdict sort (`VERDICT_SORT_RANK`) unchanged.

## D. "What changed" lightbox

- **AC-D1** Given a changed line's `TriangleAlert` lightbox (`BoardChangeTable`), Then the
  body renders `BoardChangeWasNowTable` (`omitHeader`, Decision row kept) instead of the
  `label from → to` lines, followed by the suggestion lines, `Where it went` and lateness
  exactly as today.
- **AC-D2** The dialog description reads `Only the fields that moved, then the suggestion.`
  (unchanged); the Was/Now table shows only fields that moved (`changedFieldsOf`), never a
  row of dashes.
- **AC-D3** At 375px the table fits inside the dialog (`max-w-[min(28rem,calc(100vw-2rem))]`)
  with no horizontal scroll.
- **AC-D4** `OrderInquiryQtyAnnotationDialog` is untouched, and the shared table keeps
  its `dd/mm/yyyy` dates (`formatDateInMalaysia`) so that dialog reads exactly as today.
  Review round 1 (22 Sep): the unmoved-row omission of AC-D2 is a board-lightbox-only
  prop (`onlyMovedFields`); the OI dialog keeps printing Qty and Date rows as on main, so
  a qty-only amendment keeps its Date row and an import-recovered row with equal numbers
  never renders an empty box.
- **AC-D6** (review round 1) In a stacked lightbox each change keeps its own
  `productChangedFrom`, `Where it went`, lateness and moved-transfer lines under its own
  table; a change that moved nothing prints the existing "moved this line without changing"
  prose in place of an empty table; only the suggestion lines read off the newest change.
- **AC-B14** (review round 1) "Undo all" applies the AC-B13 rule to every batch-named line
  (back to `Change proposed`, still counted for Confirm); its toast reads `N lines undone`.

## E. Evidence

- **AC-E1** agent-browser run via sidebar on the lane stack: list view row with `PO` chip,
  Verdict trio on a Suggested and a Change proposed line, Reject popover open with the typed
  reason, pill `Rejected` after submit, Verdict column dragged wider, lightbox at 375px and
  1280px. Screenshots under `documentation/plans/scm/evidence/board-verdict-actions-chips/`.

## D (cont.) One icon per cell

- **AC-D5** Given a line with more than one pending change row for the same column (two
  batch rows whose `date` moved), When the row renders, Then ONE `TriangleAlert` icon shows
  in that column, and its lightbox lists every pending change for the line newest first,
  each as its own Was/Now table under a `Changed <dd/mm/yyyy>` heading (batch row's own
  timestamp when the annotation carries one, else no heading), then the latest suggestion
  lines. Owner finding 22 Sep: two and three icons on one row read as noise.

## B (cont.) Undo returns to the pre-mark

- **AC-B13** Given a line the open change batch names (it was seeded `Change proposed`),
  When the planner saves a decision (`Saved`) and then clicks Undo, Then the server draft is
  deleted and the pill reads `Change proposed` again (session draft
  `{ verdict: 'approved', preMarked: true }`), still counted toward Confirm. A line the
  batch does not name goes back to `Suggested` as today. Owner finding 22 Sep: "it becomes
  suggested instead of change proposed".
