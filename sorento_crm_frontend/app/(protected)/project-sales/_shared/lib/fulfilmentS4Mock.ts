/**
 * ============================================================================
 * SCM Fulfilment Planning - SAVED DECISIONS PHASE 1 MOCK OVERLAY (S4, PLAN-scm-fulfilment-
 * feedback-2sep.md, ruling R-F)
 * ============================================================================
 * The board GET is LIVE - this mock stands in for the ONE thing Phase 2 has not built yet:
 * a server that remembers a Save (`so_supply_decisions.state = 'draft'`) across a reload,
 * another device, or another planner. `fulfilmentPlanningService.ts` routes
 * `putLineDraft` / `deleteLineDraft` through the two functions below instead of a real
 * `PUT` / `DELETE`, and stamps every `getPlanningBoard` response with whatever this module
 * is currently holding, so Phase 1 can be walked end to end in a real browser before Phase 2
 * writes the table.
 *
 * THE CONTRACT PHASE 2 OWES (delete this file and its callers the day it ships):
 *
 *   PUT    /project-sales/fulfilment-planning/lines/{contribution_key}/draft
 *          body { decision: BoardDecision } -> BoardLineDraft
 *   DELETE /project-sales/fulfilment-planning/lines/{contribution_key}/draft -> 204
 *          Upsert / remove one row of a new `so_supply_decision_drafts` table, one per
 *          contribution key (order id, line no, item code, bucket key), NOT
 *          `so_supply_decisions` - see the PLAN's S4 "Deviation (3 Sep)" note for why a
 *          per-line draft cannot live on that table. Confirm deletes the drafts it promotes
 *          in the same transaction.
 *
 *   PlanningBoard.contributions[].draft / BoardCell.contributions[].draft : BoardLineDraft
 *          Every contribution the drafts table carries a row for, stamped onto BOTH the
 *          board's top-level `contributions` and each cell's own copy - the two already have
 *          to agree about `covered`/`decision` for the same reason (see `withContribution` in
 *          `FulfilmentBoardPanel.test.tsx`).
 *
 *   BoardLineDraft.stale : boolean
 *          Whether the engine has re-suggested this line since it was saved (AC-4.4). The
 *          REAL comparison is server-side: the drafts table row keeps a snapshot of what
 *          `propose_line` returned at save time, and the GET compares it against what
 *          `propose_line` returns today. Mocked here as a JSON-string comparison of
 *          `contribution.proposed` at save time against `contribution.proposed` now - the
 *          client-only stand-in for that stored snapshot, thrown away with this file.
 * ============================================================================
 */
import type {
  BoardCell,
  BoardContribution,
  BoardDecision,
  BoardLineDraft,
  PlanningBoard,
} from '../types/fulfilmentPlanning.types';

interface MockDraftEntry {
  draft: BoardLineDraft;
  /** `JSON.stringify(contribution.proposed ?? null)` at save time - see the module doc's
   * `stale` paragraph. */
  basisSignature: string;
}

/** Module-level, shared across every board this tab opens - Drafts are SHARED, not per
 * user (R-F), and the real table will be too. Reset on a full page reload, same as any
 * other in-memory mock; the "reload persists" half of AC-4.2 is Phase 2's to prove for real. */
const mockDrafts = new Map<string, MockDraftEntry>();

/**
 * Save decision (PUT). `savedBy` is the session user's display name; `proposedNow` is
 * `contribution.proposed` at the moment of the click, captured by the caller so this module
 * never has to know how to find a contribution by key.
 */
export function mockPutLineDraft(
  key: string,
  decision: BoardDecision,
  savedBy: string,
  proposedNow: unknown,
): BoardLineDraft {
  const draft: BoardLineDraft = {
    decision,
    saved_by: savedBy,
    saved_at: new Date().toISOString(),
  };
  mockDrafts.set(key, {
    draft,
    basisSignature: JSON.stringify(proposedNow ?? null),
  });
  return draft;
}

/** Undo (DELETE). A key nobody saved is a no-op, matching the real endpoint's idempotence. */
export function mockDeleteLineDraft(key: string): void {
  mockDrafts.delete(key);
}

/**
 * Stamps `draft` (with a freshly computed `stale`) onto every contribution the map holds a
 * row for, on BOTH the board's own `contributions` and each cell's copy. A contribution
 * nobody saved is returned unchanged, so `board.data.contributions[].draft` stays absent
 * exactly as an untouched line's does on the real payload.
 */
export function withMockDrafts(board: PlanningBoard): PlanningBoard {
  if (mockDrafts.size === 0) return board;
  const stamp = (contribution: BoardContribution): BoardContribution => {
    const entry = mockDrafts.get(contribution.key);
    if (!entry) return contribution;
    const stale =
      entry.basisSignature !== JSON.stringify(contribution.proposed ?? null);
    return { ...contribution, draft: { ...entry.draft, stale } };
  };
  const stampCell = (cell: BoardCell): BoardCell => ({
    ...cell,
    contributions: cell.contributions.map(stamp),
  });
  return {
    ...board,
    contributions: board.contributions.map(stamp),
    cells: board.cells.map(stampCell),
  };
}
