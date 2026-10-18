# UAC: split SO lines into delivery splits (OI-LINE-SPLIT)

Owner OK on mock v2, 16 Oct 2026 23:47; the split screen redone to mock v4 after the 17 Oct hand test
(owner OK 14:10): `documentation/mockups/OI-LINE-SPLIT/index.html`. Sections B to E are unchanged.
Plan: `PLAN-oi-line-split-16oct.md`. Words: a **split** is one part of an SO line (qty, delivery
date or Cancel, remark, the line it sits on). Never "tranche" in UI or copy.

## A. The split sheet (Fulfilment planning), mock v4

Owner hand test of #1749 FAILED the v2 grid (17 Oct ~12:40); owner OK on mock v4 17 Oct 14:10 ("Ok,
make sure the sort handler is at the leftmost, go"), Q1 drag yes, Q2-Q4 (a), Q5 (a). Mock:
`documentation/mockups/OI-LINE-SPLIT/index.html` (v4). This section replaces the v2 grid/zoom AC.

- AC-A1 Entries unchanged: "Split delivery…" in a board line's action menu and right-click menu, the
  AutoCount change lightbox button, the SO header button. Each opens ONE full-screen page for that
  line's SO, scrolled to that line, the line flashed.
- AC-A2 One table with every open line of the SO, sorted by item code, location, then base delivery
  date (then line no). Columns in order: grip (LEFTMOST), LINE (AutoCount line no), SO DATE, S/O NO,
  ITEM CODE, LOCATION, QTY (base), NEW QTY, DELIVERY DATE (base), NEW DATE | CHANGE QUANTITY, CHANGE
  DATE, REMARK, BALANCE, remove. The first line of each item has a heavier top border. There is NO
  AUTOCOUNT LINE column (owner hand test 18 Oct, answer (b)): a split goes to another line by drag only.
- AC-A2b QTY / NEW QTY / DELIVERY DATE / NEW DATE present a line's pending AutoCount change the way the
  OI email does (owner hand test 18 Oct: "present the change just like how we present in email"):
  QTY = base qty, DELIVERY DATE = base date, NEW QTY = AutoCount's qty only when the qty moved, NEW DATE
  = AutoCount's date only when the date moved, each blank otherwise. "Moved" is decided by ONE backend
  function, the same one the email's settled line uses for its Was (`handover_moves`); the API returns
  `new_qty` / `new_date` (null = blank) and the sheet only renders them. No "AutoCount now" or "Added
  in AutoCount" text anywhere. SO417636 CSK14B: line 480 417 | 14 | 20/10/2026 | 20/09/2026; line 608
  192 | 632 | 20/11/2026 | (blank); line 752 504 | 649 | 20/12/2026 | 02/01/2027; line 32 301 | (blank)
  | 20/09/2026 | (blank), "Delivered 301". A line AutoCount added prints QTY 0, NEW QTY its qty,
  DELIVERY DATE "-", NEW DATE its date.
- AC-A3 A split line shows one row per split, stacked downward; LINE to DELIVERY DATE and BALANCE are
  merged across its split rows (rowSpan; NEW QTY and NEW DATE too). A split row: grip, qty, date
  (typed DD/MM/YYYY or calendar) with its change pill, remark, remove (x). A line AutoCount added
  (base 0) cannot be split or dragged. A line other lines' splits sit on shows "+N from line M" for
  each.
  A line whose saved splits no longer act (`split_state` stale) shows an "AutoCount changed" pill
  under its delivery date; an applied line shows none (as built).
  A line AutoCount has DELIVERED IN FULL (nothing open, no splits, nothing sitting on it) is still
  listed, read-only, so the sheet shows every line like the staff Excel: QTY = its ordered qty,
  DELIVERY DATE, CHANGE QUANTITY "Delivered <qty>", no grip, not a drop target
  (SO417636 line 32: 301 @ 20/09/2026).
- AC-A4 A line that is not split ("REMAIN" in this document) shows its own QTY and DELIVERY DATE as
  plain values in CHANGE QUANTITY and CHANGE DATE (DD/MM/YYYY; the base values, also inside Confirm),
  never the word REMAIN (owner hand test, 17 Oct evening: "don't put remain, just put the value"); its
  remark editable. Clicking one of those cells, or typing a digit (either cell) or "/" (date cell) on
  it, turns the line into one split row (base qty, base date, this line) with focus in that cell (the typed key in it).
  When focus leaves a line whose only split equals its base on its own line and date, the line is
  unsplit again (its values shown plainly), its remark kept. The change pill of a split row (REMAIN /
  DELAY / ADVANCE / CANCEL, AC-A11) is the email's change word and stays. A zero-qty split is dropped when focus leaves its line and on Save.
- AC-A5 "+ Split" in BALANCE, or Ctrl/Cmd+Enter in a split row, adds a split row under the line:
  qty = what is left on the line (0 when nothing is), the line's base date, sitting on "New line";
  its qty gets focus, selected.
  Pending change default (owner hand test 18 Oct: "this should be 14 and the remaining in second line,
  the new qty will be the first value by default, this date should be the new date also"): "+ Split" on
  a line that is NOT split yet and has a pending change (a NEW QTY or NEW DATE shown, AC-A2b) starts it
  as TWO rows: row 1 on this line = NEW QTY capped at QTY, at NEW DATE (each falls back to QTY /
  DELIVERY DATE when blank); row 2 on "New line" = QTY minus row 1 (0 when nothing is left), at
  DELIVERY DATE; row 2's qty gets focus. SO417636 line 480: 14 @ 20/09/2026 + 403 @ 20/10/2026; line
  752 (504 -> 649, 20/12/2026 -> 02/01/2027): 504 @ 02/01/2027 + 0 @ 20/12/2026. With no pending change
  "+ Split" is unchanged (QTY @ DELIVERY DATE on this line + what is left). Clicking or typing in an
  unsplit line's value cell is unchanged (AC-A4). The x button, or Ctrl/Cmd+Backspace in the row, removes a
  split row at once (staged until Save; no confirm).
- AC-A6 BALANCE of a split line: "0" with a tick when its splits add up; "N left" as a draggable chip
  when short; "N over" in red when over. A line that is not split shows only "+ Split".
- AC-A7 REMOVED 18 Oct (owner answer (b)): no AUTOCOUNT LINE select and no Enter path into one. A
  split reaches another line, "New date" or "Cancel this qty" by drag (AC-A8, AC-A9) only: mouse,
  touch long-press, or the grip's keyboard pick-up (AC-A10).
  A line's PLANNED date (one AutoCount line carries one date, crew audit 17 Oct): the date of its own
  split that stays on it (not a cancel) when it is split; else the EARLIEST date of the splits from
  other lines already sitting on it; else its AutoCount date (current, else base). The drag overlay
  and the drop always show and use the same date. A typed date stays as typed; changing a line's own
  date later does not move other lines' splits already on it.
- AC-A8 Drag (Q1): the grip of a split row, the grip of a REMAIN line (the whole line) and the "N left"
  chip drag (mouse after 5 px, touch long-press, keyboard). While dragging: lines of other items or
  locations fade and are not targets; the dragged line's own block is not a target; a "New date" and
  a "Cancel this qty" drop row open under the item's last line; the overlay shows the qty, item,
  "from line N" and the target ("→ 20/11/2026 · line 608", "→ New date", "→ Cancel this qty"); the
  hovered line block is highlighted; the sheet autoscrolls slowly from a thin edge band. At 375 with
  the sheet scrolled sideways, the pinned item cell stays opaque on highlighted rows.
- AC-A9 A drop moves ALL of it at once, with no "how many" box (Q5 a). A split row: sits on the target
  line and takes that line's planned date (AC-A7); if a split of the same own line already sits there on
  that date the two merge (qty added, remarks joined). The "N left" chip: a new split of N at the
  target (merging the same way). A REMAIN line: the whole line moves. "New date": sits on "New line"
  with an empty date, focused, and Save waits until a date is typed. "Cancel this qty": a cancel
  split. A toast "Moved N to <target>" offers Undo. To move part, type the qty first, then drag what
  is left (SO417636 CSK14B 480: type 14, drag "403 left" onto line 608 -> 403 @ 20/11/2026 on 608).
- AC-A10 Keyboard: Tab / Shift+Tab move between cells; Enter or Down goes to the same column one row
  down, Shift+Enter or Up one row up; on a grip or chip: Space picks up, Down / Up next / previous
  target (the item's other lines in order, then New date, Cancel), Space or Enter drops, Escape puts
  it back. Cmd/Ctrl+Z undoes the last change.
- AC-A11 Change pill per split against its own line's base date: later DELAY, earlier ADVANCE, same
  REMAIN, cancel CANCEL.
- AC-A12 Header: "Split delivery", "<SO no> · <SO date> · <customer>", search by item code
  (ListSearchInput), a "Split lines only" switch, ONE secondary button that reads "Close" with no
  unsaved changes and "Cancel" (discards them and closes) with unsaved changes, and Save (the one
  CTA). Escape and the dialog X with unsaved changes keep the page open and say "Save or Cancel". Under it a status line:
  "<n> lines · <n> products · <n> split", then for each line that does not add up or has a split
  with no date: "<item> line <no>: N left | N over | date to fill" and "Show" (clears search and
  filter, scrolls to the line, flashes it, focuses its first cell).

## B. Exact sums and Save

- AC-B1 Every split line's splits must add up exactly to its base qty (Q2 b). A gap or over shows
  live in BALANCE and in the status line (AC-A12); Save is disabled while any line does not add up
  or a non-cancel split has no date. A zero-qty split is removed as AC-A4 says.
- AC-B2 Base qty and date of a line = the qty and date before its pending AutoCount change when one
  is pending, else its current qty and date; a partly delivered line splits only its open qty. A
  saved split keeps the base it was made against.
  When the pending change has no "before" because AutoCount ADDED the line inside the same
  still-unapplied change and edited it later (owner hand test 18 Oct, SO417636: added 417 @
  20/10/2026, then edited to 14 @ 20/09/2026), the base is the line AS IT WAS ADDED: the `to` of
  its own `added` row in that change, matched by the exact AutoCount line (never by qty, date or
  name), less what is delivered. Only a line whose newest pending row IS its `added` row reads
  "Added in AutoCount" (base 0). The sheet, the acting / stale state and Confirm read this one base.
- AC-B3 Save writes every split of the SO in one call; the server refuses (422, message names the
  line) when a line does not add up, a split sits on a line of another SO, item or location, a qty
  is not a positive number, or a non-cancel split has no date. Nothing is saved on a refusal.
- AC-B4 A line put back to one split equal to its base on its own line and date with no remark is
  "not split" (its split rows are deleted on Save).
- AC-B5 Never stuck: a failed load shows an error with Retry; a failed Save keeps the view open with
  every value and shows the server's message as a toast; Cancel discards unsaved changes.

## C. Links are explicit (Q3 a, Q4 b)

- AC-C1 A split records its own (origin) line and the line it sits on. Sits-on is only ever set by
  staff (a drop). Nothing auto-links by qty, date or name.
- AC-C2 If the line a split sits on is cancelled or deleted in AutoCount, the split falls back to
  "new line (not in AutoCount yet)"; nothing else changes.

## D. What purchasing gets (Q5 a)

- AC-D1 The OI email (Confirm and Send to purchasing): a split line prints one row per split, each
  row reading alone: LOCATION, ITEM CODE, QTY = base qty, NEW QTY = split qty, DELIVERY = base
  date, NEW DATE = split date (blank for cancel), REMARK = change word + remark. Inside Confirm a
  line's "left to tell" adds a row ("ORDER (new qty)" or "CANCEL BALANCE"). Same template as today.
- AC-D2 The OI Excel (one sheet, #1748) gets a REMARK column appended after the existing columns.
  An OI row whose line has splits sitting on it prints one row per such split (QTY = split qty,
  DELIVERY DATE = split date, REMARK = change word, "from line N" when it is another line's, and the
  remark) when they add up to the row's QTY; otherwise it prints as today with the split plan in
  REMARK. Unsplit rows print as today with REMARK empty. TOTAL QTY stays the sum of the rows.
- AC-D3 Order inquiries Lines tab: a split line shows "Split N"; expanding the row lists its splits
  (Qty, Date, Change, Sits on, Remark). Read-only.

## E. Confirm (engine)

- AC-E1 When a line's AutoCount qty went down and staff linked part of it (a split sitting on
  another line of the same SO whose AutoCount qty went up), Confirm moves that qty with its
  purchasing links and acknowledgement to the target line's OI row (a moved row whose delivery date
  changes goes back to To confirm, the 17 Sep handshake rule): no CANCEL BALANCE for the
  linked qty on the origin, no new ORDER for it on the target. Only what is left is told (SO402757:
  line 2 51 -> 2 with 49 linked to line 18; line 18 82 -> 121 is told as CANCEL BALANCE 10 only).
- AC-E2 With no stored splits Confirm behaves exactly as today (existing pure-split and netting
  tests stay green).
- AC-E3 Nothing is written to AutoCount.

## F. Phone 375

- AC-F1 At 375px the same sheet: LINE, SO DATE, S/O NO and LOCATION are hidden (the line no shows under
  the item code, the SO date and location in the title), ITEM CODE stays pinned left while the table
  scrolls sideways. Grip and chip drag by touch long-press, the only way at 375 to move a split to
  another line (SO417636 CSK14B: touch-drag the 236 row onto line 608).
- AC-F2 Usable and not clipped at 375px and 1280px.

## G. Round 3 (owner 18 Oct evening: card answers + mock v5 variant B "B, ok")

Contract source: `CARD-oi-line-split-refer-back-18oct.md` (owner answers section) and mock v5
`documentation/mockups/OI-LINE-SPLIT/index.html` sections 2 (variant B), 4, 5, 6, 7. The worked example is
SO417636 CSK14B BRW-BB, with the owner's plan:
- 480: 14 @ 20/09/2026 on 480; 236 @ 20/11/2026 dropped on 608; 167 @ 20/11/2029 dropped on 608.
- 752: 37 @ 20/11/2026 dropped on 608; 467 @ 02/01/2027 on 752.
- AutoCount: 480 417 -> 14 (20/10 -> 20/09/2026), 608 192 -> 632, 752 504 -> 649 (20/12/2026 -> 02/01/2027).

- AC-G1 **Refer back.** QTY / DELIVERY DATE show a line's figures BEFORE the AutoCount change being shown,
  and NEW QTY / NEW DATE show them after it (blank when unchanged, `handover_moves`). The change shown is the
  pending one, or, with nothing pending, the last change a Confirm applied. That last applied change stays
  shown until a newer AutoCount change arrives.
  - With nothing pending and a Confirm on record, the sheet's status line shows "Confirmed <dd/mm/yyyy>"
    once. No per-line tag.
  - SO417636 reads the same before and after the owner's Confirm: 480 417 | 14 | 20/10/2026 | 20/09/2026;
    608 192 | 632 | 20/11/2026 | (blank); 752 504 | 649 | 20/12/2026 | 02/01/2027.
- AC-G2 **Variant B layout.**
  - A split dropped on another line is drawn under the line it landed on, and its own LINE cell shows the
    line it came from (muted). Only the LINE column drops its rowSpan for those rows.
  - The origin line keeps the splits that stay on it, plus any split left on New line.
  - SO417636: 480 shows 14 @ 20/09/2026 (ADVANCE). 608 shows its own 192 @ 20/11/2026, then 236 (LINE 480)
    @ 20/11/2026, 167 (LINE 480) @ 20/11/2029 and 37 (LINE 752) @ 20/11/2026. 752 shows 467 @ 02/01/2027
    (DELAY) and 182 @ 02/01/2027.
  - No equation text and no destination labels anywhere.
- AC-G3 **AutoCount extra.**
  - On a line, AutoCount qty (NEW QTY, else QTY) minus the splits that sit on that line (its own plus those
    dropped on it) is the line's EXTRA.
  - A positive extra shows as one more row under the line at the line's NEW DATE (else DELIVERY DATE): 752
    shows 182 @ 02/01/2027, and 608 shows no extra (192 + 236 + 167 + 37 = 632).
  - An extra is not a stored split. It is not editable, and its REMARK pre-fill is "ORDER <n>".
- AC-G4 **No CANCEL from splits.**
  - No split row is ever netted into a CANCEL: not in Confirm, not in the email, not in the Excel. A split on
    New line is a delivery of that qty at its own date (ADVANCE / DELAY / REMAIN by date).
  - CANCEL appears only for an explicit cancel split ("Cancel this qty", `is_cancel`, "CANCEL BALANCE"), and
    for AutoCount cancelling a whole line ("CANCEL ALL").
  - The `_tell_splits` guard (`project_order_inquiry_service.py` ~:4441-4463) no longer drops a line with
    New-line splits to its per-line row.
  - Mock section 7: 480 with 236 and 167 on New line prints 14 ADVANCE / 236 DELAY / 167 DELAY, never
    "CANCEL 403".
- AC-G5 **REMARK pre-fill.**
  - Each split row's REMARK cell, and the extra row's, shows the text the email would print for it, muted,
    while staff have not typed one.
  - Typed text wins and is stored. Clearing it brings the generated text back.
  - The generated text comes from ONE backend function, also used by the email and the Excel, and is sent
    to the sheet by the API. No copy of the rule lives in the frontend.
- AC-G6 **Email: one row per split** (mock section 5).
  - Each split of a line prints its own row under that line, together with the line's extra row:
    QTY / DELIVERY on the line's first row only, NEW QTY = the split's qty, NEW DATE = its date, REMARK = the
    sheet value or else the generated text.
  - SO417636: 480 rows 14 / 236 / 167; 608 row 192 -> 632; 752 rows 37 / 467 / 182.
  - The generated REMARK of a line whose increase is fully explained by splits dropped on it (608) is
    "REMAIN" (crew ruling 18 Oct: its date did not move, and moved qty never reads as ORDER). It is never
    "ORDER 440", and it stays editable (AC-G5).
- AC-G7 **Excel** (worklist export): the same rows as AC-G6 in the existing layout (mock section 6), with
  REMARK = the sheet value or else the generated text. QTY and DELIVERY DATE are merged down a line's rows.
- AC-G8 **Typed dates commit on leaving the cell or Enter, never mid-typing** (`components/ui/date-picker.tsx`
  :84-92). A calendar pick commits at once. Deleting one "1" from "20/11/2026" no longer stores 20/01/2026.
- AC-G9 **Build decisions** (lead, 18 Oct; contract for the round-3 tests):
  - Each line also carries `remark_generated` for its own row, from the same `remark_for_row`. 608's is
    "REMAIN".
  - The email prints a line's later split rows with QTY and DELIVERY blank. The template lives in the DB
    (`order_inquiry_handover_default`), so this ships as the next `oihr_` migration. The shared dev DB needs
    that template update as crew SQL; it is an UPDATE, so it is held for crew/owner approval.
  - The worklist Excel gets CHANGE QUANTITY and CHANGE DATE headings before REMARK, as in the approved mock
    section 6. Existing columns are not renamed.
- AC-G10 **The Confirm engine follows the plan too** (crew ruling (a), 18 Oct: "the 403 just go to other
  places").
  - Confirm never nets a split row into a CANCEL BALANCE OI row. Split qty that is not moved onto another
    line (a split on New line, or a link move the engine declines) stays on purchasing's side as its own OI
    worklist rows at the split dates. Worklist, email and Excel then always agree.
  - SO417636 480 with 236 @ 20/11/2026 and 167 @ 20/11/2029 on New line: after Confirm, 480's live OI rows
    are 14 @ 20/09/2026, 236 @ 20/11/2026 and 167 @ 20/11/2029 (ADVANCE / DELAY / DELAY), with no CANCEL
    BALANCE.
  - An explicit cancel split still makes a CANCEL BALANCE. No "refuse Confirm" stop-gap.
  - This ships as its own build slice: red tests first, then the fix, a kill test and the reviewer.
- AC-G11 Email continuation rows (a line's 2nd+ split row) blank LOCATION and ITEM CODE as well as QTY and
  DELIVERY (mock section 5). The sheet shows no "+N from line M" text (no labels; variant B already places
  moved rows under the line they landed on).
- AC-G12 **Declined move onto a target that grew** (crew ruling (a), 18 Oct). Sometimes the engine cannot move
  a dropped split's links: the target row is placed with no link, or the target's document was received in
  full. Then:
  - the origin keeps its rows and links;
  - the target's need excludes the declined incoming qty, so the target raises no ORDER for it.
  Nothing is bought twice, nothing is cancelled, and the live OI total equals AutoCount (reviewer probe:
  133, not 182).
- AC-G13 **Review round on 89aad589bf** (reviewer NOT READY):
  - A second Confirm with no changes changes nothing: live OI qty is unchanged and no plan email goes out
    again.
  - A split saved after Confirm is checked against the line's current base.
  - Kept splits keep purchasing's links: each kept row is linked for its own qty.
  - The Excel TOTAL QTY is the rows' live qty. The 10-column reorder-run worksheet prints each row's real
    qty.
  - A line partly from stock nets as before, and the worklist, email and Excel agree for it.
  - "Confirmed <date>" uses the Malaysia date.
  - For an unsplit line, the sheet's pre-filled REMARK equals the email's, including CANCEL ALL and NEW ITEM
    CODE.
- AC-G14 **A New-line split counts as part of its own line's plan** (reviewer, 19 Oct). It is never AutoCount
  extra again. A line of 14 planned as 10 own + 4 on New line asks 14, not 18, and shows no "ORDER 4".
- AC-G15 **Editing an applied plan acts again** (crew ruling P1 (a), 19 Oct). After Confirm, a changed split
  qty or date makes the plan act on the next Confirm. That Confirm moves purchasing's rows (links kept) and
  emails the change, so worklist, email and Excel agree; this is the owner's mistyped-date fix. A remark-only
  edit changes nothing on Confirm.
- AC-G16 **A later AutoCount change on a line with kept New-line rows** (crew ruling P2 (a), 19 Oct). The
  line's own row follows AutoCount (14 -> 20). The kept New-line rows stand until staff change or remove
  them. No CANCEL from splits, ever.
- AC-G17 **A re-plan that drops kept rows is an explicit reduction** (lead, applying the crew rule "CANCEL only
  where the user explicitly reduces qty"; reviewer 19 Oct). Example: 480's confirmed 14 / 236 / 167 is
  re-planned as 10 + 4. On the next Confirm:
  - the dropped qty (403) is one CANCEL BALANCE, held on purchasing's worklist AND printed in the email;
  - each kept row keeps links only up to its own qty, and the rest is given back.
  Worklist, email and Excel agree. A line whose PO is received in full is a standing plan like any other: a
  re-Confirm sends nothing.
