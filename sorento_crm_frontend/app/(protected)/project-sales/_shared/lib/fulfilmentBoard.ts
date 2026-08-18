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
  ConfirmLine,
  ConfirmReserveComponent,
} from '../types/fulfilmentPlanning.types';
import { fromMinor, toMinor } from './supplyComposition';

/**
 * A column header with the week-commencing abbreviation taken off.
 *
 * The captain, verbatim: "what does w/c 2 Nov 2026 mean? what does w/c mean?" - and then, on
 * being offered replacements, "just remove it". Having to ask IS the verdict. The granularity
 * control already says the board is by week, so the column has nothing left to restate.
 *
 * The label is formatted SERVER-side, so this is a bridge until that lane drops the prefix: it
 * is idempotent, and does nothing at all once the server stops sending it. It is the only
 * reformatting the client does to a server label, and it exists because jargon on screen is not
 * something to wait on.
 */
export function bucketLabelText(label: string): string {
  return label.replace(/^w\/c\s+/i, '');
}

/**
 * A ranking factor named in words a planner uses.
 *
 * The chips printed `po_document_sequence absent` and `need_by_date` - database column names,
 * shown to somebody who never chose them. Same fault as "w/c", same answer: nothing on this
 * screen should need decoding. A factor nobody has named yet is humanised rather than printed
 * raw, so a new one from the policy never regresses the screen to identifiers.
 */
const FACTOR_LABELS: Record<string, string> = {
  need_by_date: 'Required date',
  document_age: 'Order date',
  customer_credit: 'Payment terms',
  demand_class: 'Demand type',
  po_document_sequence: 'Purchase order sequence',
};

export function factorLabel(key: string): string {
  const known = FACTOR_LABELS[key];
  if (known) return known;
  const words = key.replace(/_/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

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
  const committing = new Map<string, number>();
  for (const [key, decision] of Object.entries(draft)) {
    const salesOrderId = owners.get(key);
    if (!salesOrderId) continue;
    decided.set(salesOrderId, (decided.get(salesOrderId) ?? 0) + 1);
    // A REJECTED line is decided but not committed: the planner said no, and the confirm body
    // deliberately omits it so it stays undecided and keeps flowing to reorder planning.
    if (decision.verdict !== 'rejected') {
      committing.set(salesOrderId, (committing.get(salesOrderId) ?? 0) + 1);
    }
  }
  return [...orders]
    .map((order) => ({
      ...order,
      decided_count: decided.get(order.sales_order_id) ?? 0,
      committing_count: committing.get(order.sales_order_id) ?? 0,
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
  // What would be POSTED, which is not every verdict: a rejection decides a line and commits
  // nothing for it. A button reading "Confirm 2 lines" that posts one is a button that lies.
  const committing = standing.committing_count ?? standing.decided_count;
  return {
    committing,
    leaving_undecided: standing.line_count - committing,
    blocked: standing.unplannable_count,
  };
}

/**
 * The body one order's Confirm posts, built from the board's draft.
 *
 * The captain asked whether the board's Confirm did anything - "so now when i click the confirm
 * 8 lines, it won't work and won't flow to order inquiries isit?" - and it did not. This is the
 * mapping onto the endpoint that already exists (`POST .../sales-orders/{pso_id}/confirm`), so
 * the board commits through the same per-order confirmation the sheet does rather than growing
 * a second write path (13.4: the board is a LENS).
 *
 * What is NOT named is the point. A line the body omits is left UNDECIDED and keeps flowing to
 * reorder planning, which is the captain's own reason for wanting partial confirmation. So:
 *
 *   - a REJECTED line is omitted. The planner refused the proposal; committing it anyway would
 *     be the opposite of what they said, and there is no "commit nothing for this line" verb;
 *   - a line with no `project_line_id` is omitted rather than posted with a null, because the
 *     endpoint keys on it and a null would fail the whole confirmation for the others;
 *   - an unplannable line is never decided in the first place (AC-FP16), so it never arrives.
 *
 * An AMENDMENT moves the difference into Buy. The quantity a planner takes off a Reserve does
 * not evaporate: it is still owed, and somebody still has to buy it.
 */
export function confirmLinesFor(
  contributions: BoardContribution[],
  salesOrderId: string,
  draft: BoardDraft,
): ConfirmLine[] {
  const lines: ConfirmLine[] = [];
  for (const contribution of contributions) {
    if (contribution.sales_order_id !== salesOrderId) continue;
    const decision = draft[contribution.key];
    if (!decision || decision.verdict === 'rejected') continue;
    if (!contribution.project_line_id) continue;

    const owed = toMinor(contribution.qty_outstanding ?? contribution.qty);
    // The engine's own numbers when it sends them. The board now proposes what the SHEET
    // proposes - pool and borrow are considered, not just own-location reserve then buy - so
    // re-deriving a composition from the source strip would be a second, worse allocator
    // quietly disagreeing with the real one.
    const incoming = numberOr(contribution.qty_proposed_incoming, () =>
      sumSources(contribution, 'timely_spo'),
    );
    const proposedReserve = numberOr(contribution.qty_proposed_reserve, () =>
      sumSources(contribution, 'reserve'),
    );
    const reserveQty =
      decision.verdict === 'amended' && decision.reserve_qty !== undefined
        ? toMinor(decision.reserve_qty)
        : proposedReserve;
    // Whatever the Reserve and the incoming stock do not cover is bought. Derived rather than
    // read off the proposal so an amendment cannot leave a quantity owed by nobody.
    // On an unchanged proposal the server's own Buy stands; an amendment moves the quantity
    // the planner took off the Reserve into it, because that quantity is still owed.
    const buy =
      decision.verdict === 'amended' || contribution.qty_proposed_buy === undefined ||
      contribution.qty_proposed_buy === null
        ? Math.max(owed - incoming - reserveQty, 0)
        : toMinor(contribution.qty_proposed_buy);
    const reserve = reserveWarehouses(contribution, reserveQty);
    // A Reserve nobody can address is not a Reserve. Dropping the line leaves it undecided,
    // which is recoverable; posting a Reserve with no warehouse would fail the whole
    // confirmation and take the other lines down with it.
    if (reserve === null) continue;

    lines.push({
      project_line_id: contribution.project_line_id,
      timely_spo_qty: fromMinor(incoming),
      reserve,
      // The board never proposes a Borrow: it crosses locations, and the board allocates per
      // (product, location) only (13.7, deviation 8).
      borrow: [],
      buy_qty: fromMinor(buy),
    });
  }
  return lines;
}

/** The server's figure when it sent one, else the fallback. Absent is not zero. */
function numberOr(value: string | null | undefined, fallback: () => number): number {
  return value === null || value === undefined ? fallback() : toMinor(value);
}

function sumSources(contribution: BoardContribution, kind: string): number {
  return contribution.sources
    .filter((source) => source.kind === kind)
    .reduce((total, source) => total + toMinor(source.qty), 0);
}

/**
 * The Reserve, against the one warehouse a board row can reserve from.
 *
 * A board row is single-location by construction: allocation runs per (product, location) and
 * the location is the line's own (13.7). So the payload's list has one entry, and the warehouse
 * is the proposal's when there is one and the LINE's when there is not - an amendment that
 * reserves on a line the engine proposed nothing for is exactly the case where the sources
 * carry no warehouse, and reading only the sources would silently drop the planner's quantity.
 *
 * Returns null when the quantity cannot be addressed to any warehouse at all, which the caller
 * treats as "leave this line undecided" rather than posting something the server must refuse.
 */
function reserveWarehouses(
  contribution: BoardContribution,
  reserveQty: number,
): ConfirmReserveComponent[] | null {
  if (reserveQty <= 0) return [];
  const warehouseId =
    contribution.sources.find((source) => source.kind === 'reserve' && source.warehouse_id)
      ?.warehouse_id ?? contribution.fulfilment_warehouse_id;
  if (!warehouseId) return null;
  return [{ warehouse_id: warehouseId, qty: fromMinor(reserveQty) }];
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
