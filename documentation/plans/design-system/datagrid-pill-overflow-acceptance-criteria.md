# UAC: DataGrid pill cells fold to one line with a "+N" popover

- AC-PO-1: On Users & Access > People > Administrative Users, a user with several roles reads
  as one row line: the roles that fit on one line, then a "+N" chip. The row is never taller
  than a one-role row.
- AC-PO-2: Clicking "+N" (or pressing Enter/Space on it) opens a popover listing every role of
  that user, on top of the list; Escape closes it.
- AC-PO-3: On Users & Access > People > Internal Users, the Access types column behaves the
  same way (AC-PO-1 and AC-PO-2) over the contact's access types.
- AC-PO-4: On Order Inquiry detail > Lines, the SPO column's "+N" popover renders on top of
  the rows beneath it: no neighbouring row's chip or text shows through it.
- AC-PO-5: Column resize reflows the folded count live: dragging the column wider shows more
  pills and shrinks N, with no reload.
- AC-PO-6: A cell with one pill shows no "+N".
- AC-PO-7 (follow-up lane PILL-OVERFLOW-2): On Sales > Sales Teams, the Agents column's "+N"
  popover lists every agent one per line (leader first, tagged "(Leader)") through the shared
  `PillOverflowList` body, on top of the list; Escape closes it. Same read as the People pages.
