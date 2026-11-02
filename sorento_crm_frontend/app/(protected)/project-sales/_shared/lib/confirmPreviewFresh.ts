/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): the guided Confirm shows what the server holds now,
 * and says so when a line's saved decision is not what AutoCount's pending change suggests.
 *
 * Pure: no fetch, no React. `FulfilmentBoardPanel` hands it the board's lines.
 */
import { decisionWords, type BoardChangeAnnotation } from './boardChangeAnnotations';
import { contributionDecision, partsBreakdown, type SupplyPart } from './supplyVocabulary';
import type {
  BoardContribution,
  BoardDecision,
  BoardDraft,
  ConfirmEmailLine,
  ConfirmManyBody,
} from '../types/fulfilmentPlanning.types';

/**
 * The server refused a draft write because the line was saved again after the decision this
 * tab holds (409 `board_line_draft_newer`). Lives here, not in the service module, because
 * tests mock that module whole.
 */
export class LineDraftNewerError extends Error {}

/** The server's code for that refusal (`project_line_draft_service._refuse_newer`). */
export const LINE_DRAFT_NEWER = 'board_line_draft_newer';

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
 * Do two compositions say the same thing? By board row kind and qty, the way the cards group
 * them (`partsBreakdown`); the places are compared only where BOTH sides name them, because a
 * change row's composition often carries no location while a saved decision does (review
 * round 1: "Use incoming 3" against "Use incoming 3 from BRW" is the same answer).
 */
function sameComposition(
  a: SupplyPart[],
  b: SupplyPart[],
  ownLocation: string | null,
): boolean {
  const rows = (parts: SupplyPart[]) =>
    new Map(partsBreakdown([{ parts, ownLocation }]).map((row) => [row.key, row]));
  const left = rows(a);
  const right = rows(b);
  if (left.size !== right.size) return false;
  for (const [key, row] of left) {
    const other = right.get(key);
    if (!other || Number(other.qty) !== Number(row.qty)) return false;
    const places = (r: typeof row) =>
      r.places.map((place) => `${place.location}:${Number(place.qty)}`).sort().join('|');
    if (row.places.length > 0 && other.places.length > 0 && places(row) !== places(other))
      return false;
  }
  return true;
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
  if (!latest || !suggestion) return null;
  const ownLocation = contribution.fulfilment_location ?? null;
  // A bare approval composes nothing of its own: it takes the proposal (`contributionDecision`).
  const keptParts = contributionDecision(contribution, decision) ?? [];
  const kept = decisionWords(keptParts, ownLocation);
  if (!kept) return null;
  if (latest.nowParts ? sameComposition(keptParts, latest.nowParts, ownLocation) : kept === suggestion)
    return null;
  return { suggestion, kept };
}

/**
 * Runs `task` once every earlier task queued under the same key has settled, so writes on one
 * line go one at a time (review round 2, S3). `onIdle` runs when the LAST queued task for the
 * key settles; `queue` is the caller's own map (key -> the latest task's settling).
 */
export async function queuedPerKey<T>(
  queue: Map<string, Promise<void>>,
  key: string,
  task: () => Promise<T>,
  onIdle?: () => void,
): Promise<T> {
  const prior = queue.get(key);
  let settle: () => void = () => {};
  const mine = new Promise<void>((resolve) => {
    settle = resolve;
  });
  queue.set(key, mine);
  if (prior) await prior;
  try {
    return await task();
  } finally {
    settle();
    if (queue.get(key) === mine) {
      queue.delete(key);
      onIdle?.();
    }
  }
}

/**
 * CONFIRM-PREVIEW-STALE round 3: planning line id -> the purchasing email's REMARK for it, off
 * a dry run's `email_lines` (one line per row the email prints; a line told twice reads both,
 * in the email's own order, joined by " / ").
 */
export function emailWordsByLine(lines: readonly ConfirmEmailLine[]): ReadonlyMap<string, string> {
  const out = new Map<string, string[]>();
  for (const line of lines) {
    if (!line.so_line_id) continue;
    const words = (line.remark ?? '').trim();
    if (!words) continue;
    out.set(line.so_line_id, [...(out.get(line.so_line_id) ?? []), words]);
  }
  return new Map([...out].map(([id, words]) => [id, words.join(' / ')]));
}

/**
 * The email's words for one covered line: `undefined` when its order was not previewed (fall
 * back to the board's own words), `null` when the email sends no line for it.
 */
export function emailWordsFor(
  byOrder: ReadonlyMap<string, ReadonlyMap<string, string>>,
  psoId: string | null | undefined,
  line: { project_line_id?: string | null },
): string | null | undefined {
  const words = psoId ? byOrder.get(psoId) : undefined;
  if (!words) return undefined;
  return (line.project_line_id && words.get(line.project_line_id)) || null;
}

/**
 * The guided Confirm's email dry run body (review round 3, S3): the press's own body, `quiet`
 * (the server records no refusal for it), with every order that has no planning record yet
 * (an empty `pso_id`, adoption deferred) left out. `null` when nothing is left to preview.
 */
export function emailPreviewBody(body: ConfirmManyBody | null | undefined): ConfirmManyBody | null {
  const orders = (body?.orders ?? []).filter((order) => Boolean(order.pso_id));
  if (!body || orders.length === 0) return null;
  return { ...body, orders, quiet: true };
}
