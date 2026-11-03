# UAC: CONFIRM-PREVIEW-STALE

> Superseded in part (3 Nov 2026): the "AutoCount moved this line" warning with Keep / Take
> suggestion is removed by `PLAN-no-ac-moved-warning-3nov.md` (owner: a saved decision stands
> silently). Do not restore it.

Plan: `PLAN-confirm-preview-stale-2nov.md`. Owner rulings: popup = email = Excel; one bad line
never refuses an order.

- U1. Opening Confirm re-reads the board and the split sheets; the Review split prints nothing
  until both answered after the open (no cached sheet from before a Save).
- U2. When that re-read fails, the page says so with a Retry; Next, Keep, Take suggestion and
  Confirm are off until a read succeeds.
- U3. A board read whose saved draft is newer than the one this tab holds replaces the tab's
  decision and names the line in a toast; Confirm posts the newer decision.
- U4. The tab's own save is never announced as "saved again elsewhere".
- U5. The server refuses a draft save or Undo based on an older draft (409
  `board_line_draft_newer`); a request that says nothing keeps last writer wins.
- U6. A line delivered in full that a pending change names shows DELIVERY DATE = the date before
  the change and NEW DATE = after it, and no "nothing goes to purchasing" note. Its REMARK, like
  every line's, is the purchasing email's own (the press's dry run, `email_lines`): Buy 25 held
  with a date move reads "DELAY"; Reserve 5 + Buy 20 reads "DELAY, CHANGED: ORDER 25 -> ...".
- U7. A line AutoCount closed because it was delivered reads its change word, never CANCEL ALL.
- U8. A saved decision whose composition differs from the change's suggestion is flagged "AutoCount
  moved this line: suggestion X, you keep Y" with Keep / Take suggestion; the same composition
  (whatever places one side names) is not flagged; a pre-mark is never flagged; Next stays on.
- U9. (Stacked PR #2107, item 4) Plain Confirm: a delivered line's saved decision reaches
  purchasing (Confirm plans it at its ordered qty, owner ruling 14 Sep): a Buy raises its row, a
  Borrow raises its order back; only a plan qty of 0 (cancelled, returned, `qty_required` 0) is
  skipped (#1362). Nothing refuses the order. The Review split prints the saved decision's words,
  never "nothing goes to purchasing".
