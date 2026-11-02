# UAC: CONFIRM-PREVIEW-STALE

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
  the change and NEW DATE = after it, the change word, and no "nothing goes to purchasing" note.
- U7. A line AutoCount closed because it was delivered reads its change word, never CANCEL ALL.
- U8. A saved decision whose composition differs from the change's suggestion is flagged "AutoCount
  moved this line: suggestion X, you keep Y" with Keep / Take suggestion; the same composition
  (whatever places one side names) is not flagged; a pre-mark is never flagged; Next stays on.
- U9. (Follow-up PR, item 4) Plain Confirm: a delivered line whose saved decision is a Borrow tells
  purchasing its order back; a Buy on a delivered line keeps the skip; nothing refuses the order.
