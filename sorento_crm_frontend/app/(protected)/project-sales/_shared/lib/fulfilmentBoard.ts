/**
 * What the fulfilment board needs from the CLIENT, now that the server computes the board.
 *
 * Seam B owns the arithmetic: bucketing, ranking, allocation and the contribution keys all come
 * down the wire. Three things stay here because they are the client's own business:
 *
 *   - `standingsFor`, because verdicts live in the board's draft and the server always sends
 *     `decided_count: 0` (deviation 4);
 *   - `commitPreviewFor`, which turns a standing into the sentence beside its Confirm;
 *   - `amendNeedsReason`, which decides whether an edit is displacing the ranking.
 *
 * The board-CONSTRUCTION engine that used to live here (bucketing, scoring, allocation) moved to
 * `__testsupport__/boardFixture.ts` when the mock was deleted. It builds realistic boards for the
 * component tests and is not shipped: keeping it in production would be a second implementation
 * of the thing the server now owns, which is exactly the defect `priority.py` warns about.
 */
import type {
  BoardCommitPreview,
  BoardContribution,
  BoardDraft,
  BoardOrderStanding,
} from '../types/fulfilmentPlanning.types';
import { toMinor } from './supplyComposition';

/** The least a contribution has to carry for the standings to be computed from it. */
export interface StandingContribution {
  /** The SERVER's key. Never rebuilt on this side - see the tests for why. */
  key: string;
  sales_order_id: string;
  so_number: string;
  customer_name?: string | null;
  fulfilment_location?: string | null;
}

/**
 * Per order: how many of its lines in this selection carry a verdict yet.
 *
 * This is the number that makes the partial-decision reality visible (13.4). A cell holds one
 * product on one date and an order spans many lines across many dates, so approving one cell
 * almost never finishes an order.
 *
 * It reads the contribution's OWN key and never rebuilds one. The server derives `line_no`
 * (core sales-order lines have none) and owns the key format, so any disagreement about
 * bucketing between the two sides would make every rebuilt key miss - and miss SILENTLY, with
 * the draft still filling up while the counter sat at zero. Deviation 5.
 *
 * The server's `orders[].decided_count` is always 0 by design (deviation 4): verdicts live in
 * the client draft, so the count is ours to compute and the server's field is not read.
 */
export function standingsFor(
  contributions: StandingContribution[],
  draft: BoardDraft,
): BoardOrderStanding[] {
  const byOrder = new Map<string, BoardOrderStanding>();
  for (const contribution of contributions) {
    const standing = byOrder.get(contribution.sales_order_id) ?? {
      sales_order_id: contribution.sales_order_id,
      so_number: contribution.so_number,
      customer_name: contribution.customer_name ?? null,
      line_count: 0,
      decided_count: 0,
      unplannable_count: 0,
    };
    standing.line_count += 1;
    if (!contribution.fulfilment_location) standing.unplannable_count += 1;
    if (draft[contribution.key]) standing.decided_count += 1;
    byOrder.set(contribution.sales_order_id, standing);
  }
  return [...byOrder.values()].sort((left, right) =>
    left.so_number.localeCompare(right.so_number),
  );
}

/**
 * What confirming this order right now would do, and what it would leave behind.
 *
 * Confirm is NOT gated on completeness (PLAN 13.4, the captain's decision): a planner commits
 * the lines they are sure about so the undecided ones keep flowing to reorder planning. So the
 * screen owes a plain statement of the consequence instead of a disabled button, and this is the
 * number behind that sentence.
 *
 * A line that can never be decided here (its sales order states no location) is counted inside
 * `leaving_undecided` and named again in `blocked`, because it is undecided for a reason the
 * planner cannot fix on this screen.
 */
export function commitPreviewFor(standing: BoardOrderStanding): BoardCommitPreview {
  return {
    committing: standing.decided_count,
    leaving_undecided: standing.line_count - standing.decided_count,
    blocked: standing.unplannable_count,
  };
}

/**
 * Whether an amend needs a reason.
 *
 * Reducing the Reserve the rule proposed takes stock away from this line and hands it to
 * nobody in particular, so a person has to say why. Accepting the proposal unchanged does not:
 * demanding a reason for agreeing is how a mandatory field becomes a rubber stamp.
 */
export function amendNeedsReason(
  contribution: BoardContribution,
  reserveQty: string,
): boolean {
  const proposed = contribution.sources
    .filter((source) => source.kind === 'reserve')
    .reduce((total, source) => total + toMinor(source.qty), 0);
  return toMinor(reserveQty) !== proposed;
}
