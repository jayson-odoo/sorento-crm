# PLAN: guided Confirm on the Fulfilment planning board (OI-SPLIT-GUIDE)

Status: Build (Phase 2): #1794 merged 296915c7ca, branch rebased onto main 33434f19ee; tester red next. Card answered
(Q1/Q3/Q4/Q5 (a); Q2 changed by the owner to "saved lines only"), mock v1 approved by the owner 20 Oct
~10:33, crew ruling a63941103 (Confirm's server behaviour unchanged; Review labels AutoCount rows). Track:
M (new flow on an existing screen, no migration, no auth change). Lead pattern: tester red tests, one
coder (Opus: board panel state), reviewer, browser pass 1280/375 on a crew copy (SO417636 + a two-order
case), hand-test script, --handtest.

Card: `oi-split-guide-behaviour-card.md`. UAC: `oi-split-guide-20oct-acceptance-criteria.md` (the
behaviour; this plan does not restate it). Mock: `documentation/mockups/OI-SPLIT-GUIDE/index.html`.

## Journey

Owner 20 Oct ~11:14: "show the split view upon confirm, or even before confirm in fulfillment planning
... so that the user can view the split before confirm ... a guided process step by step". Then, on the
mock: "when we confirm, should confirm those saved lines only, so the split also should show the save
lines only". The planner presses Confirm (N), looks at each order's saved split edits (and can fix one),
sees every row purchasing will get (rows forced by the AutoCount book labelled as such), then confirms.

## Discovery (cited; FE = sorento_crm_frontend/app/(protected)/project-sales, P = FE fulfilment-planning/components/FulfilmentBoardPanel.tsx, L = FE _shared/lib/fulfilmentBoard.ts; line numbers on #1794's head)

- Confirm today: `board-confirm` (P:2610) -> `runConfirmAll` (P:1758): `buildConfirmOrders` -> silent dry
  run `previewConfirmMany.mutateAsync(built.body)` (P:1783) -> narrows each order to what the dry run
  answered -> `confirmMany` post -> result card `board-confirm-results` (P:2704). The dry run is fused
  into the press: the guide splits it into step 2 (build + dry run, render) and step 3 (post the narrowed
  body from step 2's answer).
- What the press sends (subagent read, spot-checked): only saved things. Body `lines` = role `post`
  (saved decision drafts, L:456-470), plus `rejected_line_ids` / `cancelled_lines`; saved split edits are
  added server-side by `_with_split_edits` (BE api/v1/projects/fulfilment_planning.py:1291, called :512 and
  :1561). Pre-marks are stripped (`draftWithoutPreMarks`, P:278-285). Side effects on unsaved lines of the
  same orders: book-cancelled lines are counted with no decision (L:1017-1019) and retired; drifted covered
  lines are dropped (`_carry_snapshot_has_drifted`, BE services/project_supply_service.py:5798) and their
  raised rows cancelled with a handover row (BE services/project_order_inquiry_service.py:5773-5786); batch
  orders auto-accept book cancels (BE services/planning_change_service.py:4428-4433). Crew ruling: keep all
  of it, show it.
- Split step source: `splitEditsByOrder` (P:1337-1358) over `splitEditsToConfirm` (L:955) = exactly the
  board's "Split edits to confirm" list and the split-edited lines the count includes.
- Read-only sheet: `OrderSplitsDialog` (FE _shared/components/LineSplitInfo.tsx:287) renders
  `LineSplitSheet readOnly` from `LineSplitService.read` payload; the board's wrapper is
  `BoardOrderSplitsDialog` (P:3340). Edit sheet: `LineSplitDialog` (P:3348).
- Stepper: `components/common/WizardSteps.tsx:20` (`steps`, `currentId`; prints only the current label
  at narrow widths), used by `leads/components/LeadWizardDialog.tsx`.
- Dry-run rows: `ConfirmManyOrderResult.inquiry_rows` (`PreviewInquiryRow`, BE schemas/project_supply.py:622:
  line_no = planning address, item_code, verb, is_new, qty, delivery_date, stock_location, note), built by
  BE project_supply_service.py:11640-11713. **Likely gap:** it lists only rows with `supply_decision_id ==`
  the NEW revision (:11674-11678); a drift-cancelled row raised under an OLDER revision may be missing.
  UNVERIFIED: the first BE test decides.

## Phase 2 contract (tester and coder share this)

BE (small; only what Review needs):
1. Dry run lists every row the press changes for the order, whichever revision raised it (UAC C3): a
   retired row of an earlier revision (drift cancel, book cancel, batch auto-accept) appears with its
   CANCEL verb. Fix in the preview builder only if the test shows it missing; the real press is unchanged.
2. `PreviewInquiryRow.autocount_change: Optional[str]` = `cancelled` | `qty` | `date` | `qty_date`, set
   only on a row whose line the press did NOT name (not in `lines`, `rejected_line_ids`, `cancelled_lines`,
   and not a split edit `_with_split_edits` added); null otherwise. Cause from the server's own facts
   (book cancel flag; the same comparison `_carry_snapshot_has_drifted` makes), one rule. Mirror the field
   in the FE type.

FE:
3. `ConfirmGuideDialog` (new, fulfilment-planning/components/): dialog + `WizardSteps`; pages = split
   pages (orders in `splitEditsByOrder`, board order) + review + confirm; Back/Next/Cancel per UAC B/C/D.
4. Split page: the read-only sheet filtered to that order's saved split edits (the #1794 line-popup view
   per line, landing lines included); reuse `LineSplitSheet readOnly` / `OrderSplitsDialog`'s body, no new
   grid. CTA opens `LineSplitDialog` on top; on save, re-read and drop an order with no edit left.
5. Split `runConfirmAll` into `previewPress()` (build + dry run, returns the narrowed orders + refusals)
   and `postPress(narrowed)` (today's post + result card + toast). Confirm (N) opens the guide; the guide
   calls them. Behaviour of the post half byte-for-byte as today (regression test on the body).
6. Review table: rows per order (UAC C2), AutoCount label from `autocount_change` (UAC C4), refusals,
   errors with Retry/Back.

Test ids (tester and coder both use these; tests drive the board panel, not the dialog's props):
`confirm-guide` (dialog), `confirm-guide-steps`, `confirm-guide-split-page` (attr `data-so` = SO
number), `confirm-guide-split-edit` (the "Split delivery <SO>" CTA), `confirm-guide-split-error` +
`confirm-guide-split-retry`, `confirm-guide-review`, `confirm-guide-review-order` (attr `data-so`),
`confirm-guide-review-row`, `confirm-guide-autocount` (the label inside a row), `confirm-guide-nothing`
("Nothing to send to purchasing"), `confirm-guide-refused`, `confirm-guide-review-error` +
`confirm-guide-review-retry`, `confirm-guide-confirm` (step 3 button), `confirm-guide-next`,
`confirm-guide-back`, `confirm-guide-cancel`. The read-only sheet keeps its #1794 test ids inside a page.
Existing board tests that press `board-confirm` and expect an immediate post now walk the guide (A1);
the tester updates them in the red commit, keeping their assertions on the posted body.

## Test list (tester writes red from the UAC; coder may not weaken assertions)

BE (`tests/scm/`, throwaway DB, no `-n` on heavy files):
- T-BE1 preview of an order with a covered line whose AutoCount qty drifted lists that line's CANCEL row
  (UAC C3); same for a book-cancelled line on a batch order.
- T-BE2 `autocount_change` = `qty` / `date` / `cancelled` on those rows, null on a named line's row and on
  a split-edit row.
- T-BE3 the real press (preview false) writes the same rows as before (pin: no behaviour change).
FE (vitest, files touched only):
- T-FE1 Confirm (N) opens the guide, no confirm call; Cancel/Escape: no call (A1, A2).
- T-FE2 split pages = orders with saved split edits only; an untouched split line of the same order is
  not shown; no saved edit -> opens at Review with two steps (B1, B2, B6).
- T-FE3 Next walks pages, Review only after the last, Back (B5); CTA opens the edit sheet; after save an
  order with no edit left drops (B4); sheet load error -> Retry, Next off (B7).
- T-FE4 Review runs the dry run once per entry with the same body the press builds; rows, transfers,
  "Nothing to send", refusals, AutoCount labels; error -> Retry/Back, Confirm unreachable (C1-C7).
- T-FE5 Confirm posts the same body today's press posts for the same board (D2), disabled while posting,
  failure keeps the guide at step 3 (D3).

## Steps
1. After #1794 merges: `git fetch origin main && git rebase origin/main` on crew/oi-split-guide; commit
   this plan + UAC.
2. Tester: red tests (`test(red):` commit alone), crew-note red-proof on the PR.
3. Coder (Opus): BE 1-2, FE 3-6 until green; touched tests only, pytest -n 2 max.
4. Kill test (revert product, same tests fail), crew-note kill-proof.
5. Reviewer (Opus). Browser pass 1280/375 on a crew copy: SO417636 alone (split page, edit, review,
   confirm, then Undo to restore) and a two-order case.
6. Push, PR, `laneboard/scripts/<PR>.md`, `--handtest`. PR body: follow-up count/press mismatch (UAC G).

## Risks
- The dry run and the post run seconds apart: the post re-checks on the server (hold-back) as today, so a
  stale step 2 cannot post more than the server allows; Review re-runs on every entry.
- A split edit saved inside the guide changes N; the guide re-reads the board before Review.
