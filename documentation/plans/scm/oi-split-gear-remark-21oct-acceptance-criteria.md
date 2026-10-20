# UAC: gear Split delivery shows a line's confirmed remark (OI-SPLIT-GEAR-REMARK)

Follow-up to #1799 (OI-SPLIT-GUIDE, UAC F25-F33), from the crew audit of b69ef8fcca (21 Oct).

Defect: on the Fulfilment planning board, gear "Split delivery" draws the Remark box of a confirmed line
that has no draft with the default words, not the remark the planner confirmed for it.
- `FulfilmentBoardPanel.tsx:2135` (`dialogRemarks`) skips every line whose facts are not editable, and a
  line with no draft is not editable (`remarkFactsOf`, `:2030-2036`), so its `confirmed_remark` never
  reaches the sheet.
- `LineSplitSheet.tsx:720-727`: the row of a line whose remark is not kept in a draft shows
  `only?.remark ?? ''` over the default, so an unsplit line with no stored split remark prints the
  default.

Words: "confirmed remark" = the planner's own REMARK the line's active revision froze
(`BoardContribution.confirmed_remark`, UAC F32). "Default" = the generated words (`saved_remark` /
`remarkGenerated`).

## H. Acceptance criteria

- H1. Gear "Split delivery" on the board, an unsplit line with no draft whose active revision froze a
  confirmed remark X: its Remark box shows X with the "edited" marker, not the default words.
- H2. Opening the dialog and closing it, or pressing Save with nothing changed, writes nothing for that
  line: no split remark is stored, no draft is saved, Confirm (N) does not change.
- H3. A split remark already stored on that line wins over X: it is what prints for the row
  (`project_line_split_service.py:517`).
- H4. Typing a new remark keeps today's storage for a line without a draft: the line's split remark (UAC
  F26), shown as typed. Leaving the box empty shows X again on blur: X is still what purchasing holds, and a
  confirmed remark is cleared by re-approving the line (UAC F33).
- H5. Unchanged: a line with no confirmed remark (default words, no marker), a line with a draft (draft path,
  UAC F25-F26, F32), split rows, delivered-in-full lines. The guided Confirm draws the same sheet, so H1-H4
  hold there too for a covered line with no draft.
- H6. SO / OI line (i) popup title reads "<item code>: split", no line number. Already on main
  (`LineSplitInfo.tsx:283`, pinned by `LineSplitInfo.test.tsx:113-131`, #1799); browser check only.

## Out of scope

- Clearing a confirmed remark from gear "Split delivery" on a line with no draft (needs a draft made from the
  frozen decision; today a re-approve does it).
