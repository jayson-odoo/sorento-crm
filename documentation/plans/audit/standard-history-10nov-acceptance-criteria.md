# UAC: STANDARD-HISTORY

Plan: `PLAN-standard-history-10nov.md`.

## Part A: OI detail Unconfirm

- AC-SH-A1: On an OI detail page with confirmed lines and nothing ticked, the gear's Unconfirm item
  is disabled, and pressing it sends nothing.
- AC-SH-A2: With one line ticked, Unconfirm sends only that line's live confirmed rows: never a
  cancelled row, never a used row, never another line's row.
- AC-SH-A3: Ticking several lines (the header checkbox ticks every line on the page) then pressing
  Unconfirm unconfirms every ticked confirmed line, as before.
- AC-SH-A4: Confirm and Auto link with nothing ticked keep their whole-OI scope (unchanged).

## Part B

To be written from the approved proposal (scout card on PR #2298) before any Part B code.
