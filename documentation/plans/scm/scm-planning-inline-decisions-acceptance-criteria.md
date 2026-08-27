# UAC - Fulfilment planning inline decisions + sales orders list tidy-up

Plan: `PLAN-scm-planning-inline-decisions.md`. Walk on `/scm/sales-orders` and `/project-sales/fulfilment-planning?orders=SO404352`, reached from the sidebar, 1280 and 375. Fixture line: SO404352 line 22, SRTWB7518, BRW-AM on hand 10, SO383850 holds 1 there, BRW pool 16.

## A. Sales orders list

- A1 The toolbar shows a primary **Start** button; opening it lists **Upload sales orders** and **Plan selected (N)** and nothing else (no "Start" heading inside the menu). With nothing selected, Plan selected is disabled; with 3 rows selected it reads "Plan selected (3)" and opens `/project-sales/fulfilment-planning?orders=<the 3 numbers>`.
- A2 The **Actions** dropdown lists Add sales order, Reset planning (N), Refresh, in that order. Add sales order opens the same form modal as before. No standalone Add button remains.
- A3 When the list is pinned to an agent, Add sales order and Upload sales orders are absent, Start still shows Plan selected.
- A4 The Source column and the Source filter both read **Upload** for uploaded orders; the detail page's Source field reads Upload too.
- A5 The Customer cell shows the customer name only; no Retail / Project sub-line anywhere in the column.
- A6 A **Document date** column sits immediately after Sales order, shows `dd/mm/yyyy`, sorts ascending and descending (server-side), and the SO number cell no longer shows a date.
- A7 A user with a saved column layout from before this change sees Document date next to Sales order, not at the far right.
- A8 At 375 the grid scrolls inside its container; the page body does not scroll sideways.

## B. Drawer numbers

- B1 Opening SRTWB7518 · 29 Jun 2026 from the matrix: the BRW-AM row shows On hand 10, **SO qty 1**, SPO qty 0, **Available 9**; the AM group subtotal Available is **9**; the Suggestion card says Use own location 9 from BRW-AM and Use BRW 15 from BRW.
- B2 No info icon or tooltip sits on any number in the location table; SO qty on the BRW-AM row is plainly 1.
- B3 On a fixture where other lines alone exceed on hand (10 on hand, 12 held by other lines) the subtotal Available reads **-2** and the Suggestion contains no Use own location component.
- B4 pytest pins it: for every contribution, the own group's subtotal `available_qty` equals the engine's `group_offer`, and a negative subtotal never coexists with a `group_take` component.
- B5 Expanding the BRW-AM row lists the documents with columns Doc, Number, Customer, Agent, Doc date, Delivery date, Qty; no `#` and no queue state; rows are ordered by delivery date ascending (SO383850 01/04/2026 before SO404352 29/06/2026); SO404352 carries a "this line" tag; Total reads 25.

## C. Contributing lines

- C1 Columns, in order: Sales order, Customer, Agent, Project, Outstanding, Delivery date, Location, Sourced from, Order inquiry, Decision. No Rank, Ordered or Delivered column, and the column picker does not offer them.
- C2 At 1280 with default column sizes the grid shows every column without a horizontal scrollbar (a vitest pins the default sizes under the dialog width; a user with a saved layout keeps their saved sizes, reset via the column picker).
- C3 The Decision cell is a pill only: Suggested, Approved, Amended, Confirmed, Rejected. A confirmed line reads **Confirmed** with no revision number.
- C4 Clicking the row expands it in place; the expanded panel shows Ordered 24 / Delivered 0 / Outstanding 24 / Incoming 0, Reserve inputs per location (BRW-AM with "9 available" beside it, BRW with "16 available"), the Borrow block, the Buy switch, the decision summary, the reason box, the system-problem checkbox and the three buttons Approve suggestion / Save amendment / Reject.
- C5 Opening a second row closes the first; if the first had unsaved edits a confirm prompt appears first.
- C6 No Amend button exists anywhere and no modal opens for amending.
- C7 Editing Reserve BRW-AM from 9 to 5 shows the hint **4 short** and Save amendment is disabled; setting BRW to 19 clears the hint, and Save enables once the reason is typed (a composition that differs from the suggestion always needs the reason, `amendNeedsReason` unchanged).
- C8 No line of the form "24 outstanding = 0 incoming + ..." appears.
- C9 Save amendment turns the pill to Amended; Approve suggestion turns it to Approved and resets the inputs to the suggestion; Reject requires a reason and turns the pill to Rejected.
- C10 Ticking "This might be a system problem" and saving shows a warning icon on the pill; after Confirm and a reload the icon is still there (the flag persisted).
- C11 A confirmed row opens read-only with an **Amend** button; pressing it unlocks the same panel; saving and confirming again keeps the pill at Confirmed.
- C12 Approve selected / Reject selected / Clear on the bulk bar still work on ticked rows.

## D. Header, confirm, transfers

- D1 The header bar shows "N to confirm · M rejected" on the left and, on the right, a gear followed by **Confirm (N)** as the last element. No Approve all, no Confirm all approved.
- D2 The gear lists Undo all and Back to sales orders; Undo all is disabled when nothing has been edited and clears every draft decision when pressed.
- D3 With nothing touched on a 3-line board, Confirm reads Confirm (3). Rejecting one line makes it Confirm (2) and the counter "2 to confirm · 1 rejected".
- D4 Pressing Confirm opens "Confirm N lines across M orders?"; confirming sends every non-rejected line: amended lines as amended, untouched lines as suggested. Rejected lines are not sent.
- D5 The Commit section (per-order cards, "Confirm this order", the Order Inquiries / stock transfer copy) no longer exists.
- D6 After the SO404352 confirm the toast reads "37 lines confirmed · 1 transfer proposed · 0 inquiry rows" (numbers per the fixture) and a **Stock transfers** panel appears **above the product matrix**, listing the 15 × SRTWB7518 BRW → BRW-AM transfer as Proposed, for SO404352 · line 22.
- D7 Approve on that row moves it to Approved and the row stays listed; Approve all proposed approves every proposed row in the panel; each action toasts and refreshes without a page reload.
- D8 Reloading the page still shows the panel with the same transfers (it lists open transfers for the orders on the board, it does not depend on the click).
- D9 A user without `inventory.stock_transfers.edit` sees the panel with no Approve buttons.
- D10 If a confirm raised Buy rows the panel's footer reads "I order inquiry rows raised" linking to Order Inquiries.
- D11 `GET /api/v1/inventory/stock-transfers?so_numbers=SO404352` returns only transfers whose line belongs to SO404352 (pytest).

## D2. Reconfirm and transfers (R16)

- D12 Approve the BRW → BRW-AM transfer on the board, then amend a different line of SO404352 and Confirm: the approved transfer keeps its number, its Approved state and its approver; the toast reports it under "kept".
- D13 Amend line 22 from 15 to 16 from BRW and Confirm: the old transfer is cancelled and a 16-unit one is proposed (or the proposed row updated, per the plan); an amendment that removes the BRW component cancels it with nothing new.
- D14 pytest covers unchanged-kept, grown, shrunk, vanished and new movements.

## E. Guard

- E1 Amending SO404352 line 22 to Reserve 15 from BRW-AM (on hand 10, 1 already confirmed by SO383850) and confirming returns 409; the row is pinned with "BRW-AM: 10 on hand, 1 already reserved by SO383850, you asked 15"; nothing on that order is written.
- E2 Reserve 9 from BRW-AM confirms (pytest both ways).

## F. Migrations and hygiene

- F1 `alembic heads` on the branch shows exactly one head; `439_decision_suspected_issue` chains on main's `438_merge_price_supplier_sets` (#348 merged the two heads while this lane was open) and adds the boolean with default false.
- F2 `response_model` for the board contribution decision and for `ConfirmResult` declares `suspected_system_issue` / `suspected_issues` (a test asserts the field is present in the JSON).
- F3 vitest and pytest for every file in plan section 5 pass; no new Playwright spec; an agent-browser evidence run over A1, B1, C4, D6, D7 is attached to the PR.
