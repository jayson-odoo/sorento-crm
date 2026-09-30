# PLAN: Fulfilment planning Confirm posts what the planner ticked, and says exactly what it wrote

Status: v3 redesign (preview inside the line grid) on owner hand-test feedback 30 Sep 2026; mock v3 awaiting owner look; v2 backend dry run and echo stand. PR #1395. Track: feature lane (FE + BE, no migration, no RBAC).
Domain: scm (fulfilment planning board)
UAC: `fulfil-confirm-scope-30sep-acceptance-criteria.md`
Lane: `crew/fulfil-confirm-scope` (crew lane FULFIL-CONFIRM-SCOPE), base `origin/main` at e26410c20.
Mockup: `documentation/mockups/fulfil-confirm-scope/index.html`
Alembic: none.

## Complaints (owner, 30 Sep 2026)

A. `?orders=SO402757`: Cyndi ticked two SRTWT6808 rows and pressed Confirm; SRTSH1040 line 8
   was confirmed too, with borrow transfer TR-000056 (BRW-BB -> BRW-IB, 100, order-back from
   SO415810 line 48). Revision 2, 6 lines.
B. `?orders=SO423409`: a planner "clicked all" and confirmed; only 6 items went through.

## Evidence (prod dump 29 Sep 19:00 UTC, restored to scratch DB `sorento_dump_0929`)

Measured, not guessed:

- SO402757 (`projects.sales_orders` 688bdd83) active revision 1, Jayson Foundryx, 22 Sep
  03:12 UTC, covers lines 5, 10, 11, 12 only.
- `projects.so_supply_decision_drafts` holds ONE draft on that order: line 8 SRTSH1040,
  verdict `approved`, saved_by Jayson Foundryx, 22 Sep 03:09 UTC (three minutes before rev 1,
  never promoted because rev 1 did not name it). Its stored borrow rows name LEENA's donors
  (SO417636, SO383872 lines 20/50).
- Board built in-process on the dump (`FulfilmentBoardService.build(["SO402757"])`): line 8 is
  `covered=False`, `draft=approved / Jayson Foundryx`, live suggestion `borrow 43 + 57 from
  BRW-BB` naming JEREMY's donors (SO396347, SO396350). Lines 6 and 9 SRTWT6808 are the two
  rows Cyndi could tick (covered by inquiry rows, no decision).
- Simulated press (`ProjectSupplyService.confirm_many`, never committed): posting lines 6 + 9
  plus line 8 writes revision 2 with 7 lines and raises transfer **TR-000056**, 100, BRW-BB ->
  BRW-IB on line 8's core line. Posting lines 6 + 9 alone writes 6 lines and no transfer.
  The transfer number, quantity and route match the owner's complaint exactly.
- SO423409 (d50faffc) revision 1, Nurain, 28 Sep 09:14:42 UTC, 8 seconds after adoption
  (the Confirm press adopts first): 8 of 16 open lines, every one `buy` with amend reason
  "D. DATE : DEC'26"; 6 of the 8 got an order-inquiry row. Draft audit rows begin 29 Sep
  00:58 UTC, so the 28 Sep press cannot be replayed row by row. On the dump all 8 remaining
  lines confirm cleanly today (simulated). Hold-back (#1362) merged 29 Sep 18:20 MYT, after
  that press.

## Root causes

1. **Confirm's scope is "every saved draft on the board", not "what I ticked"**
   (`FulfilmentBoardPanel.tsx` `runConfirmAll` -> `confirmLinesFor(contributions, so, draftWithoutPreMark)`;
   `fulfilmentBoard.ts` `confirmLinesFor`/`lineFor`). The draft map is seeded from the server on
   every board read (`contribution.draft`, panel seeding effect), so a draft saved by anybody, on
   any day, rides along with the next person's press. The tick boxes feed Decide only, and
   Decide unticks a row once it is saved (R9), so at press time the selection is empty and the
   only signal is the number in "Confirm (N)" and the dialog title "Confirm N lines across M
   orders?". That is complaint A: Cyndi's press carried Jayson's 8-day-old draft on line 8.
2. **An approved draft is re-derived from the LIVE suggestion at press time**
   (`lineFor` tail: `borrowComponents(contribution, decision.borrow)` reads
   `contribution.sources`; the saved composition contributes reasons only). Line 8 was saved
   with LEENA's donors and posted with whatever the ladder proposed at press time (JEREMY's
   donors on the dump, SO415810 in prod). Nobody approved the composition that was written.
3. **The result never names the lines it wrote.** `ConfirmResult`/`ConfirmManyOrderResult`
   carry counts only; the toast's "N lines confirmed" is derived client-side
   (`orders[].lines.length - fulfilled - heldBack`), and the results block prints "confirmed as
   revision N (K purchase rows handed over)". A scope mismatch is silent by construction.
4. Ways a press falls SHORT of what was ticked (complaint B is one or several of these; the
   28 Sep press cannot be replayed):
   - header tick box selects the current PAGE only (`components/ui/data-grid-select-column.tsx:48`,
     `toggleAllPageRowsSelected`; board list `pageSize={25}`), so "click all" on a board with
     more than 25 rows ticks 25;
   - Decide "As suggested" skips rows already saved or already confirmed (`BoardDecideControl.tsx`
     `canQuickSave`), the other ways skip rows the pick cannot cover in full (`decideComposition`);
   - server hold-back (#1362, `_write_holding_back`) drops refused lines out of the press and
     confirms the rest;
   - a draft whose line facts moved (`draft.stale`) is left out; unpostable lines (`no_mirror`,
     `no_reserve_warehouse`, `buy_reason_missing`) are left out; fulfilled lines are skipped.
   All of these already say something (toast, banner, results block), none of them names the
   lines in the same place as what WAS written.

## Design (simplest thing that works)

No new state, no new endpoint. Three changes, each on an existing surface:

S1. **Backend echoes the lines it wrote.** `ProjectSupplyService.confirm()` returns
    `lines_confirmed: [{project_line_id, line_no, item_code}]` (the `checked` lines the new
    revision froze from this payload) and `lines_carried: int` (covered lines carried forward
    untouched). `confirm_many` copies both per order. `ConfirmResult` and
    `ConfirmManyOrderResult` declare them (undeclared fields are dropped by `response_model`).
    A withdrawal-only press echoes `lines_confirmed: []`.
S2. **The pre-confirm dialog lists the lines it will post, and each has a tick box.** The
    existing AlertDialog ("Confirm N lines across M orders?") gains a list grouped per order:
    line no, item code, verdict word (Approved / Amended / Rejected), composition summary
    (e.g. "Borrow 43 + 57 from BRW-BB", "Buy 239"), and "saved by <name> <relative time>".
    A line saved by someone other than the current user, or saved before this board was
    opened, shows that fact in amber. Every box starts ticked; an unticked line is left out of
    the payload and keeps its draft (nothing else changes). The action button reads
    "Confirm N lines" and follows the ticks. Lines the press cannot post (stale, left out,
    held back by a batch) are listed under "Not posted" with their existing reasons.
S3. **The toast and the results block read the server echo.** "N lines confirmed" = the sum
    of `lines_confirmed.length` over ok orders. Under each order's result line the block lists
    the confirmed lines ("line 6 SRTWT6808 · line 9 SRTWT6808"), then "K carried forward",
    then held back / fulfilled / notices as today. When the lines posted for an order differ
    from the lines echoed (server held some back, or an older server sent no echo), the block
    says so in amber: "Posted 3, server confirmed 2: line 8 SRTSH1040 was held back".
S4. **Board list: the header tick box ticks every row, not the page.** `buildSelectColumn`
    gains an opt-in `selectAllRows` (uses `toggleAllRowsSelected`, label "Select all rows");
    only the fulfilment board list passes it. Other listings are untouched.

Not changed: which lines are POSTED for an approved draft (root cause 2). The dialog now shows
the composition that will be written, so the swap is visible before the press; reversing the
"stale is judged on facts, never the proposal" ruling is out of scope and named for the owner.

## Design v2 (owner Lavish feedback, 30 Sep 2026)

Owner, verbatim: "i don't need a popup showing what's to be confirmed, cause the list will be
exhausting, i need to know is there any autosave button, or, we can have a preview CTA before
confirm, so they can preview and finalize what will be sent to OI before confirming, so they need
to click preview first, then only can confirm, in preview, they supposed to see whatever will be
sent to the OI, and, again, I don't want any auto save and please check if there is any autosave
that causes the complaints".

Supersedes S2 of the Design section above (the dialog list is removed). S1 (server echo), S3
(results read the echo) and S4 (header tick = all rows) stand.

P1. **No confirm popup.** The AlertDialog "Confirm N lines across M orders?" and its line list
    go. Confirm writes directly once Preview has been opened.
P2. **Preview is a required step.** Header gets "Preview (N)" beside Confirm. Confirm is disabled
    ("Preview first") until a preview for the CURRENT board state has loaded; any draft save,
    undo, tick change or board refetch that changes the postable population disables Confirm
    again until the next Preview.
P3. **Preview is the server's answer, not a client list.** Preview posts the same body Confirm
    would post to `POST /fulfilment-planning/confirm-all` with `preview: true`. The server runs
    `confirm_many` exactly as for a real press and rolls every order back instead of committing,
    answering per order with `lines_confirmed`, `lines_carried`, `lines_held_back` (with
    reasons), `lines_fulfilled_skipped`, `inquiry_rows` (verb, line_no, item_code, qty,
    delivery_date, stock_location, note) and `transfers` (kind, qty, from, to, line_no). Nothing
    is derived on the client.
P4. **Preview panel is inline under the header** (same place as the results block), grouped per
    order: one row per OI row the press would raise, with a tick box (default ticked), the
    decision that produced it, and who saved that decision and when (amber when another planner
    or before this board was opened). Held-back lines and not-sent lines (stale, unpostable) are
    listed with their reason, untickable. Unticking a row removes its line from the press and
    keeps its saved decision; the Confirm label follows the ticks ("Confirm N lines").
P5. **Confirm** posts the ticked population; toast and results read the echo (S3 unchanged).

## Design v3 (owner hand test on b51a4a40c, 30 Sep 2026)

Owner, verbatim: "for the preview, actually my idea is to use the same datagrid table at the
bottom, don't need this extra section at the top, and it is supposed to be CTA (Preview)
button instead of the Confirm, Confirm should appear after preview, and in preview, the table
of the list of items should be filtered to whatever will be sent to purchasing after clicking
Confirm, and what will become stock transfer after confirm, so it needs to be a clear and
straightforward view on what will be distributed to which flow after clicking confirm".

Supersedes P4 (the inline panel). P1 (no popup), P2 (Preview required), P3 (server dry run)
and P5 (echo) stand.

Q1. Header CTA is "Preview (N)" alone. After the preview loads it becomes "Confirm N lines"
    with "Exit preview" beside it; the count follows the ticks. A population change drops
    Confirm and brings "Preview (N)" back (same fingerprint as v2).
Q2. Preview mode filters the existing "Every contributing line" grid to the rows the server
    says the press will post, keeps the tick column (untick = leave out, decision kept) and
    adds a first column "Flow": one tag per thing the server would write for that line:
    "Purchasing · <verb> <qty>" per order-inquiry row, "Stock transfer · <from> to <to> <qty>"
    per transfer. A banner above the grid sums it: "N to Purchasing · T stock transfers · H
    held back · C carried forward". Held-back rows (reason, no tick) and not-sent rows sit in
    their own groups under the ticked rows, never mixed in. Decide, Save all suggested and Undo
    all are disabled in preview. Exit preview restores the full grid.
Q3. The Stock transfers grid above stays the transfer list; in preview it also lists the
    transfers the press would propose, marked "proposed on Confirm", greyed when their line is
    unticked.
Q4. The v2 inline preview panel is removed. Results block after Confirm unchanged.

## Autosave audit (owner question, 30 Sep 2026)

There is no autosave. Every server draft write goes through one route, reached only by a click:

- Only backend writer: `PUT /fulfilment-planning/lines/{key}/draft`
  (`app/api/v1/projects/fulfilment_planning.py:393` -> `project_line_draft_service.save_draft`,
  `app/services/project_line_draft_service.py:233`, an upsert keyed by core line). Grep of
  `app/` finds no other `SOSupplyDecisionDraft(` / `save_draft(` writer; the undo reconstruct
  states it never writes one (`project_supply_undo_reconstruct_service.py:631`).
- Only frontend caller: `FulfilmentBoardPanel.tsx:854` inside `decide()`, fired by: the row
  editor's "Save decision" button (`BoardLineDecisionPanel.tsx:604`), the verdict chips
  (`BoardVerdictActions.tsx`), the Decide strip (`BoardDecideControl.tsx`, one PUT per ticked
  row), the cell dialog's bulk verbs (`BoardCellBreakdownDialog.tsx`), and the header's
  "Save all suggested" (`FulfilmentBoardPanel.tsx:1990`, `decideMany`). No timer, blur,
  navigation or mount effect calls it.
- Not writers: planning-change pre-marks (`FulfilmentBoardPanel.tsx:684`, `preMarked: true`)
  are local only and never posted (S5); the board-read seeding effect
  (`FulfilmentBoardPanel.tsx:738`) copies server drafts into the screen and writes nothing.
- What SO402757 hit: an explicit Approved save by Jayson Foundryx on line 8 (22 Sep 03:09 UTC)
  that revision 1 three minutes later did not name. Saved drafts are shared and persistent by
  design (R-F), and Confirm posts every saved draft on the board
  (`FulfilmentBoardPanel.tsx:1319`). That persistence, not an autosave, rode along with
  Cyndi's press. Preview (P3/P4) makes it visible and untickable before anything is sent.
- Nothing to remove. Owner option, not built unless asked: require a draft saved by another
  planner to be re-saved before it can be sent.

## Slices v2

6. BE: `preview: true` on confirm-all (run + rollback per order, echo OI rows and transfers) +
   pytest.
7. FE: remove the dialog list; Preview button + inline preview panel with ticks; Confirm gated
   on a fresh preview; vitest.
8. Review + browser pass + hand test script v2.

## Slices (v1, built)

1. BE: echo (`lines_confirmed`, `lines_carried`) + pytest.
2. FE lib: `confirmLinesFor` / `confirmSummaryFor` take an `excludeKeys` set; dialog rows
   built by a pure helper `confirmDialogRowsFor(contributions, draft, ...)`; vitest.
3. FE panel: dialog list + ticks, toast/results from echo, mismatch notice; vitest.
4. FE list: `selectAllRows` on the board's select column; vitest.
5. Review + browser pass + hand-test script (`laneboard/scripts/<PR>.md`) reproducing A and B
   on the crew test copy.
