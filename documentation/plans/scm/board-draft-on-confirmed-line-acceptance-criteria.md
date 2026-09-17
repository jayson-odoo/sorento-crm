# UAC: board draft on an already-confirmed line

Plan: `PLAN-board-draft-on-confirmed-line.md`

## Backend (pytest, `tests/test_fulfilment_line_draft_route.py`)

- AC-B1. PUT `/project-sales/fulfilment-planning/lines/{key}/draft` with verdict `approved` on a line an ACTIVE decision covers answers 409, code `board_line_already_confirmed`, and writes no `so_supply_decision_drafts` row.
- AC-B2. Same request with verdict `rejected` answers the same 409 and writes no row.
- AC-B3. Same request with verdict `amended` answers 200 and the row is written (the amend path is untouched).
- AC-B4. Verdict `approved` on a line NO decision covers answers 200 (regression guard for the ordinary save).
- AC-B5. A line whose only decision is SUPERSEDED is not covered: verdict `approved` answers 200.
- AC-B7. A partly confirmed order: the active decision covers line 1 only, verdict `approved` on line 2 answers 200 and its row is written.
- AC-B8. A covered line named by a row of an OPEN planning-change batch (`applied_at` null) answers 200 to verdict `approved`; once the batch is applied it answers the 409.
- AC-B9. A superseded row in an open batch still exempts (200).
- AC-B10. A pending row in an applied batch does not exempt (409).
- AC-B11. A superseded row in an applied batch does not exempt (409).
- AC-B6. The 409 message reads "This line is already confirmed. Amend it to change the decision, or undo the confirmation."

## Frontend (vitest)

- AC-F1. `BoardLineDecisionPanel`: covered contribution, draft equal to the frozen composition. Save is disabled and hovering it shows a tooltip with the AC-B6 sentence. Reject is disabled with the same tooltip.
- AC-F2. `BoardLineDecisionPanel`: covered contribution, draft that differs from the frozen composition with a reason typed. Save is enabled.
- AC-F3. `useConfirmManyMutation`: when the mutation rejects, the planning board and fulfilment-planning queries are invalidated.
- AC-F4. `FulfilmentBoardPanel`: a board read where a contribution is `covered` with no server `draft`, while the local draft map holds an `approved` entry for its key, drops the local entry and the pill reads `Confirmed`.
- AC-F5. AC-F4 does not drop a key whose save or delete is still in flight.
- AC-F6. A board deep-linked to an APPLIED batch does not uncover that batch's lines: pill reads `Confirmed`, Save disabled.

## Browser (agent-browser, lane stack, evidence under `documentation/plans/scm/evidence/board-draft-on-confirmed-line/`)

- AC-E1. Open the board via the sidebar for an order with a confirmed line. Expand a confirmed line. Save and Reject are disabled with the title. Pill reads `Confirmed`.
- AC-E2. Amend the same line (change a quantity, type a reason), Save. Pill reads `Saved`, header counts 1 to confirm.
- AC-E3. Undo on that line. Pill returns to `Confirmed`, header 0 to confirm.
- AC-E4. 375px and 1280px: panel buttons are not clipped, and the tooltip is fully on screen at 375px.

## Definition of done

Touched pytest and vitest green locally, CI full suite green, reviewer clean, evidence screenshots committed, PLAN Status updated, one PR against main, owner go before merge.
