/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): the guided Confirm shows what the server holds now,
 * and says so when a line's saved decision is not what AutoCount's pending change suggests.
 *
 * Pure: no fetch, no React. `FulfilmentBoardPanel` hands it the board's lines.
 */
import { decisionWords, type BoardChangeAnnotation } from './boardChangeAnnotations';
import { decisionParts } from './supplyVocabulary';
import type {
  BoardContribution,
  BoardDecision,
  BoardDraft,
} from '../types/fulfilmentPlanning.types';

/**
 * The keys whose server draft was saved AFTER the one this tab's local decision stands on
 * (`savedAt`: key -> the `saved_at` this tab last read or wrote). A key with no local
 * decision, a bare pre-mark, a key whose own write is on the wire (`busy`) or one this tab has
 * no record of is left alone: the seeding effect's own rules cover those.
 */
export function newerServerDraftKeys(
  local: BoardDraft,
  savedAt: ReadonlyMap<string, string>,
  contributions: readonly Pick<BoardContribution, 'key' | 'draft'>[],
  busy: (key: string) => boolean = () => false,
): Set<string> {
  const out = new Set<string>();
  for (const contribution of contributions) {
    const server = contribution.draft;
    if (!server?.saved_at) continue;
    const held = local[contribution.key];
    if (!held || held.preMarked || busy(contribution.key)) continue;
    const mine = savedAt.get(contribution.key);
    if (!mine) continue;
    const serverTime = Date.parse(server.saved_at);
    const mineTime = Date.parse(mine);
    if (Number.isFinite(serverTime) && Number.isFinite(mineTime) && serverTime > mineTime) {
      out.add(contribution.key);
    }
  }
  return out;
}

/** What the guide says for a line whose saved decision differs from AutoCount's suggestion. */
export interface SuggestionMoved {
  /** The pending change's suggestion in board words, e.g. `Buy 3`. */
  suggestion: string;
  /** The saved decision in the same words, e.g. `Borrow 3`. */
  kept: string;
}

/**
 * A warning, never a refusal (owner ruling "one bad line never refuses an order"): the line
 * a pending AutoCount change names carries a SAVED decision (not the board's own pre-mark)
 * whose words differ from what that change suggests (`annotation.now.decision`, what Apply
 * would post). `null` when there is nothing to say.
 */
export function suggestionMovedOf(
  contribution: BoardContribution,
  decision: BoardDecision | undefined,
  annotations: readonly BoardChangeAnnotation[] | undefined,
): SuggestionMoved | null {
  if (!decision || decision.preMarked) return null;
  if (decision.verdict !== 'approved' && decision.verdict !== 'amended') return null;
  const latest = [...(annotations ?? [])].reverse().find(
    (annotation) => !annotation.closed && annotation.now.decision,
  );
  const suggestion = latest?.now.decision ?? null;
  if (!suggestion) return null;
  const kept = decisionWords(
    decisionParts(contribution, decision),
    contribution.fulfilment_location ?? null,
  );
  if (!kept || kept === suggestion) return null;
  return { suggestion, kept };
}
