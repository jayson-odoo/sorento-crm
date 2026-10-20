# UAC: OI-SPLIT-GUIDE (guided Confirm on the Fulfilment planning board: view the split before Confirm)

Card: `oi-split-guide-behaviour-card.md`. Mock (owner-approved 20 Oct ~10:33 with the Q2 change):
`documentation/mockups/OI-SPLIT-GUIDE/index.html`. Plan: `PLAN-oi-split-guide-20oct.md`.

Answers: Q1 (a), Q3 (a), Q4 (a), Q5 (a) (crew a62743794, owner "the rest I am ok"). Q2 CHANGED by the
owner (Lavish, verbatim): "Actually when we confirm, should confirm those saved lines only, so the split
also should show the save lines only". Crew ruling a63941103: Confirm's server behaviour is unchanged
(the AutoCount book is truth); Review lists every row Confirm will send and labels the rows that do not
come from a saved line as AutoCount changes, so nothing unsaved goes unseen.

Words: a **saved split edit** is a line whose saved split plan differs from the last applied plan and
that the next Confirm applies: exactly the lines in the board's "Split edits to confirm" list
(`splitEditsToConfirm`, `_shared/lib/fulfilmentBoard.ts:955`; `splitEditsByOrder`,
`FulfilmentBoardPanel.tsx:1337`). A **saved line** of this Confirm is a line the press names (a saved
decision draft in `lines`, `rejected_line_ids`, `cancelled_lines`) or a saved split edit.

## A. Entry
- A1. Confirm (N) opens the guide dialog instead of posting. Same button, same N, same disabled state at
  N = 0 (no guide reachable).
- A2. Cancel, Escape or the dialog's close writes nothing (no confirm call, no draft change).
  Exception, same as today's press: an order never planned before is adopted when Review builds the
  dry run (`buildConfirmOrders`, adopt now), and stays adopted after Cancel. Adoption confirms nothing
  and sends nothing to purchasing (lead ruling 20 Oct on reviewer S4).
- A3. The dialog title names the orders of this Confirm ("Confirm SO417636, SO424910"); the stepper is
  the existing `WizardSteps`.

## B. Step 1 Split (only when this Confirm has a saved split edit)
- B1. One page per order of this Confirm that has at least one saved split edit; an order with none gets
  no page. Order of pages = board order.
- B2. A page shows the read-only split sheet from #1794 (`LineSplitSheet readOnly`, same columns and
  look) with ONLY that order's saved split edits of this Confirm, each as the #1794 line popup shows a
  line (UAC E3 of #1794: the line and the lines its splits land on). A split line of the same order that
  is NOT edited (equal to the applied plan) is not shown.
- B3. Page header: SO number, the "Saved, not confirmed" badge, "N split line(s)" (singular for 1), and
  one CTA "Split delivery <SO>".
- B4. The CTA opens today's edit sheet (`LineSplitDialog`) on top of the guide. After its Save the page
  re-reads: changed values show; if the order no longer has a saved split edit, its page drops and the
  guide moves to the next page (or Review). Closing the edit sheet without saving changes nothing.
- B5. Next walks the pages one by one ("Next order", then "Next: Review" on the last); Review is reached
  only after the last split page (Q5 a). Back returns to the previous page.
- B6. No order of this Confirm has a saved split edit: no Split step. The guide opens at Review and the
  stepper shows two steps (Review, Confirm).
- B7. The split sheet fails to load: the page says so with Retry; Next stays off for that page; Back and
  Cancel work.

## C. Step 2 Review (what purchasing will get, nothing written)
- C1. Entering Review (first time, and again after Back) runs the existing dry run with exactly the body
  today's Confirm press builds (`previewConfirmMany`, `preview: true`); a loading state shows while it
  runs. No new endpoint.
- C2. Per order, a table of the dry run's `inquiry_rows`: line, item code, location, qty, delivery date,
  remark (the row's verb in the words the board already prints; a row the press retires, `state`
  cancelled, reads CANCEL), and its `transfers` (kind, qty, from, to) when there are any. An order with no
  row says "Nothing to send to purchasing". (No "new qty"/"new date" columns: the dry run row has one qty
  and one date, tester finding 20 Oct.)
- C2a. The line number in Review (rows and transfers) and in admin Simulate's "Would write" list is
  AutoCount's line number, the one the board and the split sheet print (SO417636: 480), never the
  planning address (560). The dry run rows and transfers carry `so_line_no` (core line's number, else the
  mirror's: `display_line_nos`, project_line_split_service.py:1420); the browser prints
  `so_line_no ?? line_no`, the board's own rule (browser pass 1 finding, 20 Oct).
- C3. Every row Confirm will send is listed, INCLUDING rows from lines nobody saved: a line the AutoCount
  book cancelled (counted with no decision, `fulfilmentBoard.ts:1017-1019`; batch orders auto-accept it,
  `planning_change_service.py:4428-4433`), and a covered line whose AutoCount qty or date drifted (dropped
  from the revision, `project_supply_service.py:5798`, its raised row cancelled with a handover row,
  `project_order_inquiry_service.py:5773-5786`). If today's dry run leaves any of these out, the dry run
  is fixed so Review is complete.
- C4. A row that does not come from a saved line of this Confirm carries a plain label: "AutoCount
  cancelled", "AutoCount changed qty", "AutoCount changed date" (or "AutoCount changed qty and date").
  Rows from saved lines carry no such label. The cause comes from the server (one rule), never re-derived
  in the browser.
- C5. An order the dry run refuses, or that the press would drop as having nothing to confirm, shows
  its reason (the result card's words, e.g. "has nothing to confirm") and is left out of step 3, as the
  result card does today. It never shows as confirmable rows (reviewer S1).
- C6. The dry run fails (network or server): Review shows the error with Retry and Back; the Confirm step
  cannot be reached.
- C7. Every order refused or left with nothing to confirm (the press's narrowed order list is empty):
  nothing is posted, the guide closes and today's result card shows the
  refusals exactly as a refused press does now (same words, admin failing-lines table, Go to line, Reload,
  History). Refusals render in ONE place (the result card), never rebuilt inside the dialog (lead ruling
  20 Oct, revised after the tester found ~10 planningWhy specs on that card). Some refused, some ok: Review
  names each refused order with its reason (C5), Confirm is reachable, and today's result card still lists
  the refusals after the post.

## D. Step 3 Confirm
- D1. A summary line ("2 orders: SO417636 (1 row), SO424910 (9 rows). Nothing has been sent yet.") and one
  button "Confirm N order(s)".
- D2. The button posts exactly what today's press posts (the body narrowed by step 2's dry run answer,
  `FulfilmentBoardPanel.tsx:1783-1838`), shows today's result card (`board-confirm-results`) and toast,
  and closes the guide.
- D3. The button is disabled while posting (no double post). A failed post shows today's error toast and
  leaves the guide open at step 3 with the button enabled again.

## E. Unchanged
- E1. Confirm's server behaviour (what it confirms, carries, drops, retires), the board count, "Split
  edits to confirm", the gear items, admin Simulate confirm, Undo.
  Deliberate change (reviewer S3): admin Simulate's "Would write" list shares the dry-run rows, so it now
  also lists the rows an older revision raised that the press retires; they print CANCEL (from `state`),
  not their original verb.
- E2. Permissions: the guide uses the same calls with the same permission as Confirm.

## L. Layout (was F; renamed 20 Oct so F is the owner rework)
- L1. 1280: dialog per the mock; the sheet scrolls inside its own box.
- L2. 375: full-screen dialog, the stepper prints only the current label (`WizardSteps`), the sheet and
  review tables scroll horizontally inside their own box, footer buttons always visible, no page
  horizontal scroll.

## F. Owner hand test 20 Oct (phone, c024bf4056) = REWORK: the review IS the split view
Supersedes B6, C1-C7 (the dry-run rows table, transfers, AutoCount labels) and D1's wording. A, B1-B5, B7
mechanics and D2-D3 stay. Owner (verbatim): "i thought it is the split view? All these transfers dont need
to be there, need to reuse the component, i want the flow is like they review the split, adjust if
necessary, then confirm" and "All the saved lines shoild appear in the preview, be it use brw or order back
or use own location, just like our email to purchasing". Plan crew-note 6288395500.
- F1. Two steps: "Review split", then "Confirm". The guide shows no dry-run table, no transfers table and
  no AutoCount labels.
- F2. Step 1: one page per order in this Confirm (every order the press covers, board order). The page is
  the #1794 read-only split sheet (`LineSplitSheet readOnly`, same columns and look as "View splits") and
  lists EVERY line this Confirm covers for that order (the lines `countsInPress` counts), whatever its
  supply: own location, BRW pool, Borrow, Order back, Cancel SO, book cancel. No other line of the order.
- F3. A split line shows its split rows as today. A line with no split shows ONE row (its qty and date)
  whose Remark is the purchasing email's own words for its saved decision, computed by the server with the
  email's function (`saved_line_remark` / `_saved_line_parts`, project_order_inquiry_service.py:548-640),
  e.g. "USE MWH 294 & USE BRW-BB 113", "USE BRW 522 & ORDER 294", "ORDER BACK"; never rebuilt in the
  browser. A covered line that is delivered in full shows its saved words, not "Delivered N". A covered
  line the split read does not return today (book-cancelled, or no planning line) still gets one row.
- F4. Page header: SO number, "Saved, not confirmed", "N line(s)" (singular for 1), and the CTA "Split
  delivery <SO>" (B4: edit sheet on top, page re-reads after Save).
- F5. Next walks every page; the Confirm step is reached only after the last page (Q5 a). Back works.
- F6. Step 2: "N order(s): SO417636 (2 lines), ... Nothing has been sent yet." and "Confirm N order(s)",
  which runs today's press unchanged (silent dry run, narrowing, post, result card, toast; refusals and
  "nothing to confirm" land on the result card as today). Disabled while posting; a failed post keeps
  step 2 open with the button enabled again.
- F7. The split read fails: the page says so with Retry, Next stays off, Back and Cancel work.
- F8. The owner's case (dev data): SO417636 alone with its 2 saved Approve drafts gives one page with
  AutoCount line 384 CB6633 and line 400 TPE-9101 as one row each with the email's words; with the 167
  edit saved, line 480 also shows (its split rows). Line 752 is not shown.
- F9. Code: the unused `PreviewInquiryRow.autocount_change` is removed. The dry-run builder fixes stay
  because admin Simulate's "Would write" uses them (retired rows read CANCEL, AutoCount line numbers).
- F10. Review round 3 (reviewer NOT READY on ff468ae078, lead ruling): the email words do NOT ride the shared
  split read (`LineSplitService.read` stays exactly as on main, so the #1794 edit sheet and SO/OI popups never
  see a book-cancelled line as editable). Each covered line's one-row remark comes from the server on the
  board's own line data: a saved draft's words from `saved_line_remark` (the email's function), a covered
  book-cancelled line with no draft reads the email's cancel word. Every covered line therefore gets its row,
  including on an order not yet adopted (no split read) and for a book-cancelled line.
- F11. Incoming stock prints the SPO number(s) the email prints (arrival on or before the required date at
  the line's own location, the email's rule), not "INCOMING". Known difference kept: stock the email spreads
  over sibling locations of a group reads as one part here (the email's group ladder is not rebuilt for the
  preview).
- F12. Test strength: at least one test saves a draft, confirms it for real, and compares the guide's words
  with the words the confirmed revision's frozen snapshot gives the email.
- F13. Owner hand test 2 (phone, ada23cbb92) = REWORK, verbatim: "I should be able to split here and it should
  only show the one that are saved, so it is actually wrong to show all items in split delivery view, it is
  expected only those that are saved appear here only". "Split delivery <SO>" opened from the guide shows ONLY
  the lines this Confirm covers for that order, plus the lines their saved splits already sit on; never the
  whole order. No "Split lines only" toggle and no search there, so no way to list other lines. Same edit
  sheet (`LineSplitDialog`), same Save; after Save the guide page re-reads. The board's own "Split delivery"
  (gear) is unchanged and still lists every line. Plan crew-note 6289817954.
- F14. Next stays off while a page is still reading its split data (never "seen" before it has loaded).
- F15. A covered saved Reject on an already-confirmed line shows the purchasing email's own word for that
  withdrawal (server, the email's function), never a blank Remark.
- F16. In the scoped dialog (F13) everything counts and points at the shown lines only: the header line count
  and the problems list cover exactly the lines on screen (never "12 lines" with 2 shown, never a problem on a
  hidden row). Reviewer nit on ca0da0a80a, taken before the hand test.
- F17. F15 follows the email exactly: a saved Reject reads the withdrawal word only when the line has rows the
  email would cancel (raised order inquiry rows); a Reject on a reserve-only line, which the email prints
  nothing for, has no words.
- F18. Owner hand test 3 (phone, 402a274558) = REWORK, verbatim: "Can i just split it here instead of clicking
  split and go to another page to actually split?" The Review split page itself is the editable split sheet:
  the same editor as the board's "Split delivery" (one component, `LineSplitEditor`, hosted by the board
  dialog and inline by the guide), scoped to the page's covered lines (`onlyLineIds`), with its balance /
  problems bar and its own Save on the page. After Save the page stays and re-reads. The guide has no "Split
  delivery <SO>" button and opens no dialog. Unsplit covered lines keep the email's words in Remark; a line
  with nothing to split (delivered in full) and every line of an order not yet adopted stay read-only rows.
  The board's own "Split delivery" looks and behaves as before. Plan crew-note on #1799 (round 4).
- F19. While the page has unsaved split edits, Next and Confirm are off and one line says "Save or undo your
  split changes first". Save failing shows the error and keeps the edits (never stuck). At 375 the qty and
  date boxes are reachable by sideways scroll inside the sheet; no page sideways scroll.
- F20. F17 extended to the email's own cancel rule: a saved Reject reads "CANCEL ALL" when the email would
  cancel the line's rows: raised rows, and placed or partly linked rows whose links are cascade-only
  (project_order_inquiry_service.py ~5885-5900). A reserve-only line still has no words.

## G. Out of scope
- Making Confirm never touch unsaved lines (crew option b).
- Follow-up (PR body): an order whose only counted line is book-cancelled may count in N but press
  "Nothing could be sent" (`FulfilmentBoardPanel.tsx:1440-1455` vs `:1770-1772`; reading only, UNVERIFIED).
