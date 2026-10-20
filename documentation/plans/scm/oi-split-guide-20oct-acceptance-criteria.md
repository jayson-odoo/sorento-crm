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
- C5. An order the dry run refuses shows its reason and is left out of step 3, as the result card does
  today.
- C6. The dry run fails (network or server): Review shows the error with Retry and Back; the Confirm step
  cannot be reached.
- C7. Every order refused: nothing is posted, the guide closes and today's result card shows the
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
- E2. Permissions: the guide uses the same calls with the same permission as Confirm.

## F. Layout
- F1. 1280: dialog per the mock; the sheet scrolls inside its own box.
- F2. 375: full-screen dialog, the stepper prints only the current label (`WizardSteps`), the sheet and
  review tables scroll horizontally inside their own box, footer buttons always visible, no page
  horizontal scroll.

## G. Out of scope
- Making Confirm never touch unsaved lines (crew option b).
- Follow-up (PR body): an order whose only counted line is book-cancelled may count in N but press
  "Nothing could be sent" (`FulfilmentBoardPanel.tsx:1440-1455` vs `:1770-1772`; reading only, UNVERIFIED).
