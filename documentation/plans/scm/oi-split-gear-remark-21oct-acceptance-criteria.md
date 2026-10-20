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
- H7 (reviewer round 1 blocker). The server's email words win over a confirmed remark wherever the next
  Confirm tells purchasing them: a line with a saved Reject or Cancel draft (`saved_remark` "CANCEL ALL", UAC
  F15, F20) and a book-cancelled line with no draft ("CANCEL ALL", UAC F10) show those words, never X and never
  "edited", in the gear dialog and on the guided Confirm's Review page. Only a line with NO draft hands over
  its confirmed remark (`remarkFactsOf`, `FulfilmentBoardPanel.tsx:2030-2041`; also fixes the guide's read-only
  words, `ConfirmGuideDialog.tsx:42`).
- H8 (reviewer round 1). Typing exactly X back into the box of a no-draft line with no stored split remark
  stores nothing: the dialog is not dirty and Save sends no split for the line. Emptying the box keeps it empty
  while focused; on blur X shows again, nothing is stored and Save stays disabled.

## Out of scope

- Clearing a confirmed remark from gear "Split delivery" on a line with no draft (needs a draft made from the
  frozen decision; today a re-approve does it).
