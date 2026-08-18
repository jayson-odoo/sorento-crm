/**
 * What the fulfilment board needs from the CLIENT, now that the server computes the board.
 *
 * Seam B owns the arithmetic: bucketing, ranking, allocation, the selection-scoped totals and
 * the contribution keys all come down the wire. Three things stay here because they are the
 * client's own business:
 *
 *   - `standingsFor`, because verdicts live in the board's draft and the server always sends
 *     `decided_count: 0` (deviation 4). Everything ELSE about a standing is read, not counted:
 *     anything counted off the cells is window-scoped and therefore wrong;
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

/**
 * Which sales order each contribution key belongs to.
 *
 * Accumulated by the panel across every board it has shown, rather than rebuilt from the cells
 * currently on screen: a verdict given on a cell that a later window no longer displays is
 * still that order's verdict, and dropping it would make the counter fall as the planner
 * scrolled. The key itself is never parsed - the server owns its format (deviation 5).
 */
export type ContributionOwners = Map<string, string>;

/**
 * Per order: how many lines it has IN THE SELECTION, and how many of them carry a verdict yet.
 *
 * This is the number that makes the partial-decision reality visible (13.4). A cell holds one
 * product on one date and an order spans many lines across many dates, so approving one cell
 * almost never finishes an order.
 *
 * `line_count` and `unplannable_count` are the SERVER's, off `board.orders`, which is built
 * from every row of the selection. They used to be counted from the cells on screen, and at day
 * granularity the cells are a 30-day window: a forty-line order read "3 of 3 lines decided" and
 * the Confirm beside it promised to leave nothing behind. A count that shrinks when you change
 * the view is not a count of anything.
 *
 * Only `decided_count` is ours, because verdicts live in the client draft; the server's field is
 * always 0 by design (deviation 4) and is overwritten here. A draft key nobody owns counts for
 * nobody rather than being guessed at.
 */
export function standingsFor(
  orders: BoardOrderStanding[],
  owners: ContributionOwners,
  draft: BoardDraft,
): BoardOrderStanding[] {
  const decided = new Map<string, number>();
  for (const key of Object.keys(draft)) {
    const salesOrderId = owners.get(key);
    if (!salesOrderId) continue;
    decided.set(salesOrderId, (decided.get(salesOrderId) ?? 0) + 1);
  }
  return [...orders]
    .map((order) => ({
      ...order,
      decided_count: decided.get(order.sales_order_id) ?? 0,
    }))
    .sort((left, right) => left.so_number.localeCompare(right.so_number));
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
