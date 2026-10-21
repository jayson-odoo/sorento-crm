# PLAN: gear Split delivery shows a line's confirmed remark (OI-SPLIT-GEAR-REMARK)

Status: PR #1810. Small fix track (frontend only, no migration, no auth or RBAC change). Red-first in three
rounds (416ed08e3e + f1a50520e5, 72efa950a8, 017c64538a), fixes 3d0c23701b, 09b0022b73, 2ffab3203f, kill held
each round; reviewer READY on 2ffab3203f (UAC H1-H10). Next: browser 1280/375 on the crew copy, CI.

UAC: `oi-split-gear-remark-21oct-acceptance-criteria.md` (H1-H10; this plan does not restate it).

## Journey

A planner opens gear "Split delivery" for an order whose line they confirmed with their own remark. The
Remark box shows that remark, marked edited, not the default words, so the dialog matches what
purchasing was told.

## Change

1. `FulfilmentBoardPanel.tsx` `dialogRemarks` (`:2122-2150`): also hand the sheet the facts of a line with
   no draft when it has a confirmed remark (`editable: false`, `own` = the confirmed remark), so the editor
   knows it. The remark of such a line still saves as a split remark (`handlers.remark`), never through
   `saveLineRemarks`.
2. `LineSplitSheet.tsx` (`:720-727`), the row of a line whose remark is not kept in a draft: show the stored
   split remark, else the line's own (confirmed) remark, else the default; the "edited" marker when the
   shown value is not the default. Display only: the confirmed remark is never written into the split
   draft, so Save sends nothing new for an untouched line (H2).

## Tests (vitest, red first)

- Board gear dialog (or the editor with the board's `lineRemarks` shape): unsplit no-draft line with
  `confirmed_remark` X shows X + "edited" (H1); Save with no change sends no remark for it (H2); stored
  split remark wins (H3); typed remark goes to the split remark (H4); a line with no confirmed remark keeps
  the default (H5).
- Neighbours: the touched files' existing suites (`LineSplitSheet`, `LineSplitEditor`, `FulfilmentBoardPanel`,
  `ConfirmGuideDialog`, `LineSplitInfo`).

## Browser (crew copy, 1280 + 375)

Confirm one line with an edited remark, reopen gear "Split delivery": the box shows it, marked edited.
Undo the confirm with the app's own action afterwards and check `email_outbox` has no pending row left from
it. SO / OI (i) popup title has no line number (H6).
