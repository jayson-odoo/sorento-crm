/**
 * CONFIRM-PREVIEW-STALE (owner, 2 Nov 2026): the guided Confirm shows what the server holds now.
 * A saved decision stands silently: nothing compares it with AutoCount's suggestion
 * (NO-AC-MOVED-WARNING, owner 3 Nov 2026).
 *
 * Pure: no fetch, no React. `FulfilmentBoardPanel` hands it the board's lines.
 */
import type {
  BoardContribution,
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
 * (an empty `pso_id`, adoption deferred) left out. `onlyPsoId` (CONFIRM-REMARK-FIX) keeps the
 * order on screen alone: a dry run costs the order's whole Confirm, so the guide never pays
 * for the pages nobody is looking at. `null` when nothing is left to preview.
 */
export function emailPreviewBody(
  body: ConfirmManyBody | null | undefined,
  onlyPsoId?: string | null,
): ConfirmManyBody | null {
  const orders = (body?.orders ?? []).filter(
    (order) => Boolean(order.pso_id) && (onlyPsoId == null || order.pso_id === onlyPsoId),
  );
  if (!body || orders.length === 0) return null;
  return { ...body, orders, quiet: true };
}
