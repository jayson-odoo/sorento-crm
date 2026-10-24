# UAC: Fulfilment planning names SO line numbers (SO-LINE-NUMBERS, 22 Oct 2026)

Plan: `PLAN-so-line-numbers-22oct.md` (alongside).

"SO line number" = the core `SalesOrderLine.line_no` (AutoCount's own number, what the order's
Lines tab and the board's Line column show). "Internal number" = the planning order's own
`ProjectSalesOrderLine.line_no`. Fallback, unchanged from #1362 item 5: a line whose core has no
number (or no core) shows the internal number.

Example data (dev copy): SO401624, internal 11 = SO line 224 (SRTWB242), internal 9 = SO line 304
(SRTSA-SS).

- **AC-1 Borrow dialog title.** Opening Borrow on SO401624's SRTWB242 line reads
  "Borrow for line 224", on the board and on the per-order sheet.
- **AC-2 Reserve dialog title.** "Add a reserve location for line 224" for the same line.
- **AC-3 Order-back notes.** Every order-back note written at Confirm names the SO line numbers:
  the borrowing line (`lent 1 to SO401624 line 304`) and the donor line (`Order-back: SO40xxxx
  line <donor SO line> lent ...`), for donor-order, location and group borrows alike.
- **AC-4 Donor names.** Wherever a donor order's line is named (Borrow dialog candidate list,
  cell breakdown, sheet card, ladder borrow reason, board composition text, the refusal when a
  borrow cannot be held), it is the donor's SO line number.
- **AC-5 Superseded donor reason.** `Borrowed by SO<ref> line <n>` names the borrower's SO line.
- **AC-6 Planning history and change rows.** The history sheet, the planning-change table, the
  change refusal table and released-document / reallocation notices name SO line numbers.
- **AC-7 Board toasts and Confirm result.** Decide toast, discard toast, "already fulfilled"
  list, simulate / cancel / confirm echoes, line blockers and the pile queue name SO line numbers.
- **AC-8 Transfers.** The board's transfers panel `so_line_no` is the SO line number.
- **AC-9 Keys unchanged.** No match key, sort, id or stored identifier changes meaning: every
  existing `line_no` field keeps carrying what it carried; the SO number travels as
  `so_line_no` beside it.
- **AC-10 Fallback.** A line with no core line number still shows its internal number (no
  "line None", no blank, no "line 0").
