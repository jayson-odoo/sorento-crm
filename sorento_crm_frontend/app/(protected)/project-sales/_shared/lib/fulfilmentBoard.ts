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
  BoardAxisRow,
  BoardCell,
  BoardCommitPreview,
  BoardContribution,
  BoardDraft,
  BoardOrderStanding,
  BoardRowAxis,
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
export function commitPreviewFor(
  standing: BoardOrderStanding,
  /**
   * How many lines the body would actually carry. Pass it whenever the body is known: a
   * decided line with no mirror on the planning record cannot be posted either, and only the
   * body knows that.
   */
  postable?: number,
): BoardCommitPreview {
  // What would be POSTED, which is not every verdict: a rejection decides a line and commits
  // nothing for it. A button reading "Confirm 2 lines" that posts one is a button that lies.
  const committing = postable ?? standing.committing_count ?? standing.decided_count;
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
 * The Reserve, one component per warehouse the engine drew on.
 *
 * A line can carry TWO reserve components at two different warehouses - its own location and
 * the dealer pool - and each has to be addressed by ITS OWN id. This is the part no display
 * string could have carried: the pill reads "BRW-BB", the payload needs two UUIDs, so the
 * warehouse is read off the SOURCE and never off the location label.
 *
 * An AMENDMENT is taken off the components in the order the engine proposed them, each capped
 * at what it proposed, and anything the planner adds beyond the whole proposal lands on the
 * first warehouse - the only one we can address it to. Whatever the Reserve does not cover is
 * Buy, computed by the caller, so a quantity a planner takes off a Reserve is never lost.
 *
 * Returns null when a quantity cannot be addressed to any warehouse at all, which the caller
 * treats as "leave this line out" rather than posting something the server must refuse.
 */
function reserveWarehouses(
  contribution: BoardContribution,
  reserveQty: number,
): ConfirmReserveComponent[] | null {
  if (reserveQty <= 0) return [];
  const proposed = contribution.sources.filter((source) => source.kind === 'reserve');
  // A reserve the server did not address is one we cannot post. Inventing a warehouse from the
  // location code would be guessing at an id, which is the one thing an id must never be.
  if (proposed.length === 0 || proposed.some((source) => !source.warehouse_id)) {
    const fallback = contribution.fulfilment_warehouse_id;
    if (proposed.length > 0 || !fallback) return null;
    return [{ warehouse_id: fallback, qty: fromMinor(reserveQty) }];
  }

  const components: ConfirmReserveComponent[] = [];
  let left = reserveQty;
  for (const source of proposed) {
    if (left <= 0) break;
    const take = Math.min(left, toMinor(source.qty));
    components.push({ warehouse_id: source.warehouse_id as string, qty: fromMinor(take) });
    left -= take;
  }
  if (left > 0 && components.length > 0) {
    // Amended ABOVE the whole proposal: the excess goes to the first warehouse, which is the
    // only one this side can name. The server rechecks the stock and refuses if it is not there.
    components[0] = {
      warehouse_id: components[0].warehouse_id,
      qty: fromMinor(toMinor(components[0].qty) + left),
    };
  }
  return components;
}

/**
 * The lines a planner DECIDED that this confirmation cannot carry, so the screen can say so.
 *
 * Adoption mirrored the order's open lines at the time it ran, so a later upload can add a core
 * line with no mirror: its order stays confirmable and that one contribution has no
 * `project_line_id`. Posting an invented id is refused outright, and silently dropping the row
 * would tell a planner they committed something they did not. The fix is a re-sync on the
 * sheet, which is somewhere else entirely - which is exactly why saying nothing would be wrong.
 *
 * A REJECTED line is not counted: it was never going to post, so it is not a loss.
 */
export function unpostableDecidedFor(
  contributions: BoardContribution[],
  salesOrderId: string,
  draft: BoardDraft,
  /**
   * Whether the order HAS a planning record. On one that was simply never adopted every line
   * lacks a mirror, which is not this problem at all - the press adopts first and the mirrors
   * appear - so naming all of them would be eleven false alarms.
   */
  isAdopted = true,
): BoardContribution[] {
  if (!isAdopted) return [];
  return contributions.filter((contribution) => {
    if (contribution.sales_order_id !== salesOrderId) return false;
    const decision = draft[contribution.key];
    if (!decision || decision.verdict === 'rejected') return false;
    return !contribution.project_line_id;
  });
}

/**
 * The lines this press INTENDS to commit, whether or not their mirrors exist yet.
 *
 * On an adopted order this is the body's own length. On one that has not been adopted the body
 * cannot be built at all yet - `project_line_id` is null everywhere until adoption mirrors the
 * open lines - so the count comes from the verdicts instead, and the press adopts before it
 * builds anything. Without this the Confirm on a fresh order would read "Confirm 0 lines" and
 * be disabled, which is exactly the dead end the captain hit.
 */
export function plannedLineCount(
  contributions: BoardContribution[],
  salesOrderId: string,
  draft: BoardDraft,
): number {
  return contributions.filter((contribution) => {
    if (contribution.sales_order_id !== salesOrderId) return false;
    if (contribution.unplannable) return false;
    const decision = draft[contribution.key];
    return Boolean(decision) && decision.verdict !== 'rejected';
  }).length;
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


/**
 * How one contribution is keyed and labelled on each row axis.
 *
 * The KEY is an id wherever an id exists and is never rendered; the LABEL is what the reader
 * sees. Keeping them apart is the whole reason two customers with one name stay two rows - a
 * board that merged them would show a single row totalling two companies' demand, and nothing
 * on screen would say so.
 *
 * Where the server sends no id the label becomes the key, which IS that merge. It is a stated
 * compromise for a payload that has not caught up, not the design: `customer_id` and
 * `project_id` are what this is written against.
 */
function axisKeyOf(
  contribution: BoardContribution,
  axis: BoardRowAxis,
): { key: string; label: string } {
  if (axis === 'sales_order') {
    return { key: contribution.sales_order_id, label: contribution.so_number };
  }
  if (axis === 'customer') {
    const label = contribution.customer_name || 'Customer not recorded';
    return { key: contribution.customer_id || `name:${label}`, label };
  }
  if (axis === 'project') {
    const label = contribution.project_label || 'Not named on the order';
    // The server's normalised key, which is a STRING because an adopted order has no project
    // registration: the project string on the order is its identity. Grouping on the raw label
    // would merge two spellings of one project and split one project written two ways.
    return { key: contribution.project_key || `name:${label}`, label };
  }
  return { key: contribution.item_code, label: contribution.item_code };
}

/**
 * The board's rows and cells for one axis, out of the contributions already on hand.
 *
 * A pivot is a different GROUPING of the same lines, never a second fetch and never a second
 * idea of what a line is - which is why a decision made under one axis is still that line's
 * decision under another.
 *
 * The per-cell counts are summed from per-line facts the SERVER stated (`is_past`,
 * `unplannable`, `contested`), never re-decided here. The stock position is left EMPTY on
 * purpose: on-hand and free are facts about one product at one location, and a cell holding
 * three products has no single stock position to state.
 */
export function boardAxis(
  axis: BoardRowAxis,
  // The SERVER's cells, not a flat list of contributions: the bucket a line sits in is a fact
  // about the cell, so flattening first would lose the date and lump a year into one column.
  cells: BoardCell[],
): { rows: BoardAxisRow[]; cells: BoardCell[] } {
  const rows = new Map<string, BoardAxisRow>();
  const grouped = new Map<string, { row: BoardAxisRow; bucket: string; lines: BoardContribution[] }>();

  for (const cell of cells) {
    for (const contribution of cell.contributions) {
      const { key, label } = axisKeyOf(contribution, axis);
      if (!rows.has(key)) rows.set(key, { key, label });
      const cellKey = `${key}|${cell.bucket_key}`;
      const existing = grouped.get(cellKey);
      if (existing) existing.lines.push(contribution);
      else {
        grouped.set(cellKey, {
          row: rows.get(key) as BoardAxisRow,
          bucket: cell.bucket_key,
          lines: [contribution],
        });
      }
    }
  }

  const pivoted: BoardCell[] = [...grouped.values()].map((entry) => ({
    // Labelled by what the reader sees, keyed by what cannot collide.
    item_code: entry.row.label,
    row_key: entry.row.key,
    bucket_key: entry.bucket,
    total_qty: fromMinor(
      entry.lines.reduce(
        (total, line) => total + toMinor(line.qty_outstanding ?? line.qty),
        0,
      ),
    ),
    locations: [],
    contributions: entry.lines,
    unplannable_count: entry.lines.filter((line) => line.unplannable).length,
    contested_count: entry.lines.filter((line) => line.contested).length,
    past_count: entry.lines.filter((line) => line.is_past).length,
  }));

  return { rows: [...rows.values()].sort(byLabel), cells: pivoted };
}

/** Sales-order numbers, customer names and project labels all read best in their own order. */
function byLabel(left: BoardAxisRow, right: BoardAxisRow): number {
  return left.label.localeCompare(right.label);
}

/**
 * Whether a row survives the board's search box.
 *
 * The captain asked for all four: "i also need sales order search, project search, customer
 * search". A ROW stays when ANY of its lines matches ANY of them, and the cells in that row
 * keep ALL their contributions - filtering inside a cell would print a total that is not the
 * cell's, which is the same rule that keeps the selection totals still under a filter.
 */
export function rowMatchesSearch(
  row: BoardAxisRow,
  contributions: BoardContribution[],
  search: string,
): boolean {
  const needle = search.trim().toLowerCase();
  if (!needle) return true;
  if (
    row.label.toLowerCase().includes(needle) ||
    (row.description ?? '').toLowerCase().includes(needle)
  ) {
    return true;
  }
  return contributions.some((contribution) =>
    [
      contribution.so_number,
      contribution.customer_name,
      contribution.project_label,
      contribution.item_code,
    ].some((field) => (field ?? '').toLowerCase().includes(needle)),
  );
}


/**
 * What a cell says about its own ranking, from ONE place.
 *
 * "The active policy separates none of these rows" is TRUE whenever nothing separated them, but
 * under the fair policy the usual cause is not the policy at all: one sales order's lines in one
 * week share their required date, their document date and their payment terms, so of course
 * they tie. Reading that as a policy failure sent people looking for a broken weighting.
 *
 * So the sentence is chosen by what actually happened, and it lives here rather than in the two
 * components that show it, because a cell reading one thing while the banner reads another is
 * how two explanations of one fact appear.
 */
export function rankingNote(
  cell: Pick<BoardCell, 'contributions' | 'distinct_order_count' | 'rank_separates'>,
): { cell: string; note: string } | null {
  if (cell.rank_separates) return null;
  const note =
    cell.contributions.length === 1
      ? 'Only line in this cell'
      : (cell.distinct_order_count ?? 0) === 1
        ? 'Same sales order; line order decided which line was served first'
        : 'The active policy separates none of these rows';
  return { cell: 'Not ranked', note };
}
