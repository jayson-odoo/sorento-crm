# UAC: DataGrid drag / range select (GRID-DRAG-SELECT)

Owner answers, 27 Oct (all final): Q1 (a) A + B + D in the shared DataGrid; Q2 (a) a drag can
untick, the first box pressed decides; Q3 (b) phone: press and hold a box, then drag; a normal
swipe keeps scrolling; Q4 (a) Odoo-style "Select all N" on Contacts now, rollout cost as a
crew-note; Q5 (a) cap 1,000, link reads "Select first 1,000 of N".

Every list that renders a row checkbox through `buildSelectColumn` or `DataGridTableRowSelect`
gets A, B, B-touch and D. C is Contacts (`/user-management/contacts`) only in this lane.

## A. Shift+click

- AC-A1: tick row 2, Shift+click row 6: rows 2 to 6 are ticked; works upward too.
- AC-A2: the range takes the last clicked box's state (unticked anchor unticks the range).
- AC-A3: rows that cannot be selected are skipped; Shift+click never opens a row.

## B. Drag on the checkbox column (mouse, pen)

- AC-B1: press row 2's box, move over rows 3 to 6, release: rows 2 to 6 ticked, nothing opens.
- AC-B2: pressing a ticked box unticks the run instead.
- AC-B3: moving back restores the rows the pointer leaves; rows skipped by a fast move fill in.
- AC-B4: a press on any other cell never starts a drag: text there stays selectable for copy.
- AC-B5: the list toolbar and table do not move while the drag runs.

## B-touch. Press and hold, then drag (phone, Q3 b)

- AC-T1: a finger swipe that starts on a box scrolls the list and ticks nothing extra.
- AC-T2: a tap on a box ticks that one row (unchanged).
- AC-T3: holding a finger still on a box for about half a second starts a drag; moving the
  finger down/up over other rows then ticks or unticks the run exactly like AC-B1 to AC-B3.
- AC-T4: a finger that moves more than a few pixels before the hold fires is a scroll: no drag.
- AC-T5: while a held drag runs the page does not scroll; on release scrolling works again.
- AC-T6: lifting the finger before the hold fires leaves the tap behaviour of AC-T2.

## D. Keyboard

- AC-D1: on a row box, ArrowDown / ArrowUp move focus between row boxes, stepping over locked
  rows, stopping at the ends; Space toggles (native).
- AC-D2: Shift+ArrowDown / Shift+ArrowUp give the next row the last clicked box's state.

## C. Select all matching (Contacts)

- AC-C1: ticking the header box ticks this page and shows "All N on this page selected." with a
  link "Select all T records" (T <= 1,000) or "Select first 1,000 of T" (T > 1,000, comma grouped).
- AC-C2: the link fetches the matching contacts with the list's filters, search and sort, page
  size 1,000, and ticks them; the strip reads "1,000 selected" (or "All T selected") and the
  banner "First 1,000 of T matching records are selected." with "Clear selection".
- AC-C3: bulk actions (Add tag, Remove tag, Link customers, Copy access) and Export act on every
  selected contact, not just the page.
- AC-C4: changing any tick leaves the all-matching mode and keeps only this page's ticks.
- AC-C5: Clear selection, or changing a filter / search, leaves the mode and clears the ticks.
- AC-C6: a failed fetch shows its error toast and leaves the page selection as it was.
