# Behaviour card: guided split view before Confirm (next PR after #1794, size M)

**Answered 20 Oct:** Q1/Q3/Q4/Q5 (a) (crew a62743794; owner ~10:33 "the rest I am ok"). Q2 CHANGED by the
owner: "Actually when we confirm, should confirm those saved lines only, so the split also should show the
save lines only" = the split step shows only saved, unconfirmed split edits; orders with none get no page.
Crew ruling a63941103: Confirm's server behaviour stays; Review labels rows not from a saved line as
AutoCount changes. Mock v1 approved. Behaviour now lives in `oi-split-guide-20oct-acceptance-criteria.md`.

Owner 20 Oct ~11:14 (verbatim): "the next thing we need to do is to show the split view upon confirm, or
even before confirm in fulfillment planning, the CTA is to split view the split delivery, so that the
user can view the split before confirm. My point is I want them to be able to view the split before they
really go and confirm, so I need this to be a guided process step by step for them."

## Today (cited; FE = sorento_crm_frontend/app/(protected)/project-sales, P = fulfilment-planning/components/FulfilmentBoardPanel.tsx)
- Confirm (N) (`board-confirm`, P:2606-2619) calls `runConfirmAll` (P:1758) at once: no dialog, no step.
  It silently runs a dry run first (`previewConfirmMany`, same body with `preview: true`, P:1779-1784,
  hook `_shared/hooks/useFulfilmentPlanning.ts:533`), then posts (P:1838); the result card is
  `board-confirm-results` (~P:2700-2900).
- That dry run already returns, per order, what purchasing will get without writing anything:
  `inquiry_rows` (line, item, verb, new, qty, date, location, note) and `transfers`
  (BE schemas/project_supply.py:622, :672-725; confirm-all `preview` api/v1/projects/fulfilment_planning.py:481,
  same EDIT permission as Confirm).
- The split view is only reachable from the board gear ("View splits <SO>", read-only sheet from #1794;
  `BoardOrderSplitsDialog.tsx`), one order at a time; editing is "Split delivery <SO>" (`LineSplitDialog`).
- A step-by-step dialog already exists: `components/common/WizardSteps.tsx` (steps + current), used by
  `leads/components/LeadWizardDialog.tsx`.
- One Confirm covers every order on the board (`buildConfirmOrders`, confirm-all runs each order alone).

## Rules (proposed)
1. **Confirm (N) opens the guide** instead of posting at once. Same count, same button.
2. **Three fixed steps** (the existing WizardSteps stepper in one dialog): 1 Split, 2 Review, 3 Confirm.
   Back is allowed; Cancel (or Escape) closes the guide and writes nothing.
3. **Step 1 Split (required).** For each order in this Confirm, the read-only split sheet from #1794
   (saved split lines only), with one CTA "Split delivery <SO>" that opens today's edit sheet on top; after
   its Save the step refreshes. An order with no split line shows "No split lines" and the same CTA.
   Several orders: one order per page (Next walks them), so each one is seen before Review.
4. **Step 2 Review.** What purchasing will get, per order, from the dry run the press already makes (rows
   with the email's words: ORDER / CHANGE QUANTITY / CHANGE DATE / CANCEL, qty, date) and the stock
   transfers. Nothing is written. An order the dry run refuses shows its reason and is left out, as the
   result card does today.
5. **Step 3 Confirm** is today's Confirm (same body, same result card, same toast). Nothing else changes.
6. **Never stuck.** If the dry run fails, Review shows the error with Retry and Back; Confirm stays off.
7. Unchanged: the board count, "Split edits to confirm", the gear items, admin Simulate confirm, Undo.

## Real examples (dev DB sorento_cagent_stack)
| # | Board | Step 1 Split | Step 2 Review |
|---|-------|--------------|---------------|
| E1 | SO417636 alone, after the owner moves 167 to 20/11/2029 | read-only sheet: line 480 (14 / 236 / 167) and 752 (37 / 467 / extra 145); "Saved, not confirmed" | the 167 row at 20/11/2029 plus whatever other saved decisions the board holds (exact rows UNVERIFIED until a dry run on the copy) |
| E2 | SO424910 alone (pending AutoCount: SRTSP124 line 16 76 -> 2, eight new lines 4 + 7 x 10 = 74) | "No split lines" + "Split delivery SO424910": the planner can lay the 74 onto the new lines so purchasing sees moves instead of CANCEL 74 + ORDER 74 | the rows the dry run builds for that change |
| E3 | SO345263 alone (14 pending AutoCount rows, no split) | "No split lines" + CTA | its rows |
| E4 | SO417636 + SO424910 planned together | page 1 SO417636, Next, page 2 SO424910 | both orders' rows, one block each |

## Edge cases
- Confirm (0): the guide is not reachable (button disabled as today).
- A huge order (255 lines): the split step lists saved split lines only, so it stays short.
- The planner edits a split in step 1 and Saves: the board count may change; Review re-runs the dry run.
- A batch order (pending upload on other lines, #1794 A12): unchanged rules, the guide only shows them.

## Questions (at most 5, each with a recommendation)
Q1. **Where the guide starts.** (a) Confirm (N) opens it (Split -> Review -> Confirm); (b) a separate
"Review splits" button in the board bar must be done before Confirm turns on. **Rec (a)**: one door,
the planner cannot skip it, nothing new on the bar.
Q2. **Which orders get the split step.** (a) every order in the Confirm (empty ones show "No split lines" +
the CTA); (b) only orders with split lines or an AutoCount qty change. **Rec (a)**: the point is to look
before confirming, and E2 is exactly the order that should have been split but was not.
Q3. **Review step.** (a) include it (from the dry run Confirm already makes, no new endpoint); (b) only
Split then Confirm. **Rec (a)**: it is the "view before you really go" the owner asked for, at no cost.
Q4. **Editing inside the guide.** (a) "Split delivery <SO>" opens today's edit sheet on top and the step
refreshes after Save; (b) the guide is read-only, edits only from the board gear. **Rec (a)**.
Q5. **"Required".** (a) Next stays off until each order's page has been shown (multi-order: one page each);
(b) one "I have checked the splits" tick. **Rec (a)**: no extra click to fake it.

## Build notes (lead)
- No backend change expected (dry run and read-only sheet exist); FE: a `ConfirmGuideDialog` built from
  WizardSteps + the read-only sheet (`OrderSplitsDialog` body) + a review table + today's `runConfirmAll`.
- Delete the dead pre-confirm helper `confirmDialogRowsFor` (`_shared/lib/fulfilmentBoard.ts:1180`, test-only
  users) or reuse it for step 2 if its rows fit.
