# PLAN: fulfilment board - a left-out line is loud, reachable, and fixable

Status: in progress, fix round 3 after re-review. Track: small fix (FE only, no migration, no endpoint, no auth change).
Branch `fix/board-confirm-left-out`, worktree `sorento_crm-board-confirm-leftout`.
UAC: `board-confirm-left-out-acceptance-criteria.md`.

## Journey (owner, 21 Sep 2026, SO420745 on prod)

CS saves decisions on a 12-line order and presses Confirm. Eleven lines flip to Confirmed,
line 32 (SRTWT9610-GM, discontinued, suggestion Buy 3) stays Saved. The only notice is one
amber sentence above the cards, easy to miss, with nothing to click. CS opens line 32, types
the reason, presses Save decision - the reason box empties and the red blocker returns. The
line can never be confirmed.

Owner: "confirming silently is dangerous"; "we should have a banner to raise attention, with
hyperlink to go to that line directly"; "the decision and suggestion are the same, I just need
to provide the reason for buying discontinued items, so we should accept this also".

## Measured cause

1. **Reason wipe.** `BoardLineDecisionPanel.tsx` `save()`: the draft equals the suggestion, so
   `matchesSuggestion` is true and the approving branch sends
   `decisionFromAmendDraft(suggestionDraftFrom(contribution), '')`. `suggestionDraftFrom` seeds
   `buy_reason` from `buy?.cs_reason ?? ''`, so the typed `draft.buy_reason` is never sent.
   The draft save succeeds, then `setDraft(suggestionDraftFrom(contribution))` clears the
   box. `matchesSuggestion` (`fulfilmentBoard.ts`) compares quantities only, which is right:
   a reason is not a change of composition. The same loss applies to a reason typed on a
   suggested borrow row (`row.reason`).
2. **Quiet notice.** `FulfilmentBoardPanel.tsx` renders `unpostableNotices(...)` as a bare
   `<p className="text-sm text-amber-700">` with no link.
3. **Verdict not sortable.** `FulfilmentBoardListView.tsx` verdict column uses
   `accessorFn: () => ''`.

## Change

1. Approving save carries the reasons the planner typed: `buy_reason` from the draft, and each
   borrow row's `reason` where the row matches a suggested borrow. Verdict stays `approved`.
   The reseed after save keeps those reasons instead of clearing them.
   `confirmLinesFor` must read the saved draft's `buy_reason` for an approved line (verify;
   fix in the same derivation if it rebuilds from the suggestion and drops it).
2. The left-out notice becomes a warning banner (existing `Alert` primitive, warning tone,
   icon), one entry per left-out line, each line name a button that switches to List view,
   expands that line's decision panel and scrolls it into view. Sentence text for the reason
   stays (`unpostableNotices` keeps producing the reason sentence; names move to the links).
   No new explanation copy.
3. After Confirm, when any line was left out, the success toast states both counts
   ("11 confirmed, 1 left out").
4. Verdict column sorts by the pill's state (Suggested, Saved, Confirmed, Rejected order),
   `enableSorting: true`.

## Out of scope (separate rulings pending)

Grid chip naming for other-group / sibling-bin stock, the modal Balance column following the
dated assignment, other-group section on-hand row and net Total.

An approved line's Order back / Document cited reach the SAVED DRAFT only (fix round 2, S2):
no verdict - amended included - has ever carried `order_back`/`cited_document` into the
`/confirm` body (`ConfirmLine` has no such field, on either `confirmLineFrom` or the sheet's
own `confirmLineFromDraft`), so wiring them all the way to Confirm is a follow-up lane, not
this one.

## Test list

- vitest `BoardLineDecisionPanel.test.tsx`: discontinued line, draft equals suggestion, reason
  typed, Save -> `onDecide` called with `verdict: 'approved'` AND `buy_reason: 'project order'`;
  after save the box still holds the reason and no blocker text renders.
- vitest same file: suggested borrow row, reason typed, approving save carries `reason`.
- vitest `fulfilmentBoard` / `confirmLinesFor`: approved draft with `buy_reason` on a
  discontinued line is NOT unpostable and its confirm line carries `buy_reason`.
- vitest `FulfilmentBoardPanel.test.tsx`: left-out line renders `role="alert"` banner with a
  button named for the line; click switches to List, opens that row's panel.
- vitest `FulfilmentBoardListView.test.tsx`: Verdict header sorts; order Suggested < Saved <
  Confirmed.
