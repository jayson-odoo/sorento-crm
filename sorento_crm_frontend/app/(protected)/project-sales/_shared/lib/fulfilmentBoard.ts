/**
 * What the fulfilment board needs from the CLIENT, now that the server computes the board.
 *
 * Seam B owns the arithmetic: bucketing, ranking, allocation, the selection-scoped totals and
 * the contribution keys all come down the wire. Three things stay here because they are the
 * client's own business:
 *
 * - `standingsFor`, because verdicts live in the board's draft and the server always sends
 *     `decided_count: 0` (deviation 4). Everything ELSE about a standing is read, not counted:
 *     anything counted off the cells is window-scoped and therefore wrong;
 * - `commitPreviewFor`, which turns a standing into the sentence beside its Confirm;
 * - `amendNeedsReason`, which decides whether an edit is displacing the ranking.
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
  BoardDecision,
  BoardDraft,
  BoardOrderStanding,
  BoardProductRow,
  BoardRowAxis,
  ConfirmBorrowComponent,
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
 * How many day columns the server renders at day granularity (deviation 7): the board's
 * `DAY_WINDOW_COLUMNS`. Paging moves by this, never by the columns that happened to come back,
 * so a window with nothing owed in it is still a page and no day is skipped or shown twice.
 */
export const DAY_WINDOW_COLUMNS = 30;

/** The first day of the window one page on from `anchor` (an ISO date), or one page back. */
export function shiftedDayWindow(anchor: string, direction: 1 | -1): string {
  const next = new Date(`${anchor}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + direction * DAY_WINDOW_COLUMNS);
  return next.toISOString().slice(0, 10);
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
  need_by_date: 'Delivery date',
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
 * Why one line stands in front of another, named.
 *
 * The policy's factors, plus the three the TIE-BREAK produces when the policy separated
 * nothing, in the queue's own order: an earlier delivery date, an earlier line of the same
 * order, or a lower sales-order number. Those three are not factors and must not read as if
 * they were - the date tie is named apart from the "Delivery date" factor, because a factor
 * label there would claim a score difference the two lines do not have.
 */
export function aheadFactorLabel(key: string): string {
  if (key === 'earlier_date') return 'Earlier delivery date (tie)';
  if (key === 'line_order') return 'same order';
  if (key === 'tie_break') return 'tie-break';
  return factorLabel(key);
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
  /**
   * The contributions an ACTIVE decision already covers, accumulated the same way `owners` is.
   *
   * A confirmed line IS decided - it is decided in the database rather than in the draft - and
   * a card reading "0 of 2 lines decided" beside an order whose first line was confirmed
   * yesterday describes nothing that is true.
   */
  covered: ReadonlySet<string> = new Set(),
): BoardOrderStanding[] {
  const decided = new Map<string, number>();
  const committing = new Map<string, number>();
  const carried = new Map<string, number>();
  const counted = new Set<string>();
  const count = (key: string, commits: boolean) => {
    const salesOrderId = owners.get(key);
    // Counted once per LINE: a covered line the planner has amended is one decision, not two.
    if (!salesOrderId || counted.has(key)) return;
    counted.add(key);
    decided.set(salesOrderId, (decided.get(salesOrderId) ?? 0) + 1);
    if (commits) committing.set(salesOrderId, (committing.get(salesOrderId) ?? 0) + 1);
  };
  for (const [key, decision] of Object.entries(draft)) {
    // A REJECTED line is decided but not committed: the planner said no, and the confirm body
    // deliberately omits it so it stays undecided and keeps flowing to reorder planning.
    count(key, decision.verdict !== 'rejected');
  }
  for (const key of covered) {
    // A covered line the planner has NOT amended is carried by the server on the next confirm
    // (the body never names it - `confirmLinesFor`), so it is decided after the press without
    // being posted by it.
    const salesOrderId = owners.get(key);
    if (salesOrderId && draft[key]?.verdict !== 'amended') {
      carried.set(salesOrderId, (carried.get(salesOrderId) ?? 0) + 1);
    }
    count(key, true);
  }
  return [...orders]
    .map((order) => ({
      ...order,
      decided_count: decided.get(order.sales_order_id) ?? 0,
      committing_count: committing.get(order.sales_order_id) ?? 0,
      carried_count: carried.get(order.sales_order_id) ?? 0,
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
  // A covered line the body does not name is CARRIED by the server into the new revision, so
  // it is decided after the press without being posted by it - and not "left undecided". Only
  // netted beside a BODY length: `committing_count` already counts the covered lines itself.
  const carried = postable === undefined ? 0 : (standing.carried_count ?? 0);
  return {
    committing,
    leaving_undecided: Math.max(standing.line_count - committing - carried, 0),
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
 * - a REJECTED line is omitted. The planner refused the proposal; committing it anyway would
 *     be the opposite of what they said, and there is no "commit nothing for this line" verb;
 * - a line with no `project_line_id` is omitted rather than posted with a null, because the
 *     endpoint keys on it and a null would fail the whole confirmation for the others;
 * - an unplannable line is never decided in the first place (AC-FP16), so it never arrives.
 *
 * An AMENDMENT moves the difference into Buy. The quantity a planner takes off a Reserve does
 * not evaporate: it is still owed, and somebody still has to buy it.
 *
 * THE BODY NAMES ONLY WHAT WAS DECIDED OR AMENDED NOW; the union is the SERVER's (13.4). A
 * confirmation supersedes the active revision, and every line that revision covers which the
 * body does not name is carried into the new one verbatim from its frozen snapshot - same
 * holds, same reasons, no re-validation. The board briefly built that union itself, re-posting
 * every covered line, and that had two holes: at day granularity the cells are a window, so a
 * covered line outside it was not re-posted and was silently un-decided; and the re-posted line
 * was rebuilt without its buy reason and re-judged against live facts, so a discontinued
 * product's covered line 422'd the confirmation of an unrelated one. So a covered line the
 * planner has not touched is NEVER posted from here.
 *
 * A confirmation carrying nothing new is not sent at all (an empty body), because there is
 * nothing to decide: the covered lines are already in the database.
 */
export function confirmLinesFor(
  contributions: BoardContribution[],
  salesOrderId: string,
  draft: BoardDraft,
): ConfirmLine[] {
  const lines: ConfirmLine[] = [];
  for (const contribution of contributions) {
    if (contribution.sales_order_id !== salesOrderId) continue;
    const built = lineFor(contribution, draft[contribution.key]);
    if (built && typeof built !== 'string') lines.push(built);
  }
  return lines;
}

/**
 * Why a decided line cannot be posted by this confirmation. Every one of these is a line the
 * server would refuse, and the confirmation is atomic across the order, so posting it would take
 * every other line down with it. It is left out and NAMED instead.
 */
export type UnpostableReason = 'no_mirror' | 'no_reserve_warehouse' | 'buy_reason_missing';

export interface UnpostableLine {
  contribution: BoardContribution;
  reason: UnpostableReason;
}

/**
 * ONE line of the body, or the reason it cannot be one, or null when nothing is to be posted
 * for it at all (undecided, rejected, or covered and untouched - none of which is a loss).
 *
 * The single place the rule lives, so the body, the notice that names what the body left out
 * and the count on the button cannot disagree about which lines those are.
 */
function lineFor(
  contribution: BoardContribution,
  decision: BoardDecision | undefined,
): ConfirmLine | UnpostableReason | null {
  // ALREADY CONFIRMED, AND NOT TOUCHED SINCE: the server carries it. Nothing to post, and
  // nothing to derive - the board proposes nothing for a covered line, and inventing one
  // would overwrite a person's composition with the engine's opinion of it.
  if (contribution.covered && !isAmendment(decision)) return null;
  if (!decision || decision.verdict === 'rejected') return null;

  const discontinued = Boolean(contribution.item_flags?.discontinued);
  const buyReason = decision.buy_reason?.trim() || undefined;

  // AN AMENDMENT COMPOSED IN THE EDITOR IS POSTED AS COMPOSED. Every warehouse and every
  // donor was chosen by a person against the balance in front of them, so there is nothing
  // left to derive - and the derivation is what used to lose them: a line the engine met
  // entirely from Buy has no Reserve source to read a warehouse off, so an amendment moving
  // it into a Reserve was dropped from the body while the row still read "Amended".
  if (decision.verdict === 'amended' && decision.reserve) {
    const buy = toMinor(decision.buy_qty ?? '0');
    if (discontinued && buy > 0 && !buyReason) return 'buy_reason_missing';
    if (!contribution.project_line_id) return 'no_mirror';
    return {
      project_line_id: contribution.project_line_id,
      timely_spo_qty: fromMinor(toMinor(decision.timely_spo_qty ?? '0')),
      reserve: decision.reserve
        .filter((row) => toMinor(row.qty) > 0)
        .map((row) => ({ warehouse_id: row.warehouse_id, qty: row.qty })),
      borrow: (decision.borrow ?? [])
        .filter((row) => toMinor(row.qty) > 0)
        .map((row) => ({
          source: row.source,
          warehouse_id: row.warehouse_id,
          donor_project_id: row.donor_project_id ?? null,
          qty: row.qty,
          reason: row.reason,
          // Ladder v2 group borrow (section E.4): round-tripped so the confirmation
          // checks this row against the donor line's live commitment, not free stock.
          donor_core_line_id: row.donor_core_line_id ?? null,
          donor_so_number: row.donor_so_number ?? null,
          donor_line_no: row.donor_line_no ?? null,
          donor_agent_code: row.donor_agent_code ?? null,
          same_agent: row.same_agent ?? false,
          donor_required_date: row.donor_required_date ?? null,
        })),
      buy_qty: fromMinor(buy),
      buy_reason: buyReason,
      // Frozen with the line. Every other component carries the sentence of the RULE that
      // produced it, and those explain a decision nobody took once a person overrode them.
      amend_reason: decision.reason,
    };
  }

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
  // An approval carries no reason, and a Buy of a discontinued product needs one (AC-B11):
  // the line is left out until the planner gives it in the editor.
  if (discontinued && buy > 0 && !buyReason) return 'buy_reason_missing';
  const reserve = reserveWarehouses(contribution, reserveQty);
  // A Reserve nobody can address is not a Reserve. Leaving the line out keeps it undecided,
  // which is recoverable; posting a Reserve with no warehouse would fail the whole
  // confirmation and take the other lines down with it.
  if (reserve === null) return 'no_reserve_warehouse';
  if (!contribution.project_line_id) return 'no_mirror';

  return {
    project_line_id: contribution.project_line_id,
    timely_spo_qty: fromMinor(incoming),
    reserve,
    // Ladder v2 (section E rules 4/5): group borrow and cross-group borrow are now
    // AUTO-PROPOSED, so an approved-as-is line can carry one - posted verbatim, the same
    // way `reserve` is, because it was the engine's own donor and reason, not a person's.
    borrow: borrowComponents(contribution),
    buy_qty: fromMinor(buy),
    buy_reason: buyReason,
    // Present only on the legacy single-number amendment, which is still an override.
    amend_reason: decision.verdict === 'amended' ? decision.reason : undefined,
  };
}

/**
 * The engine's own auto-proposed borrows (group / cross-group, section E rules 4/5),
 * posted exactly as the proposal named them - donor, warehouse and reason included. An
 * approved line never edits these, so there is nothing to re-derive: a source without an
 * addressable warehouse is dropped rather than posted as a guess, the same rule
 * `reserveWarehouses` follows.
 */
function borrowComponents(contribution: BoardContribution): ConfirmBorrowComponent[] {
  return contribution.sources
    .filter((source) => source.kind === 'borrow' && source.warehouse_id && toMinor(source.qty) > 0)
    .map((source) => ({
      source: 'other_location',
      warehouse_id: source.warehouse_id as string,
      donor_project_id: null,
      qty: source.qty,
      reason: source.reason,
      donor_core_line_id: source.donor_core_line_id ?? null,
      donor_so_number: source.donor_so_number ?? null,
      donor_line_no: source.donor_line_no ?? null,
      donor_agent_code: source.donor_agent_code ?? null,
      same_agent: source.same_agent ?? false,
      donor_required_date: source.donor_required_date ?? null,
    }));
}

/** An amendment composed in the editor, which replaces whatever was there before. */
function isAmendment(decision: BoardDecision | undefined): boolean {
  return decision?.verdict === 'amended';
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
 * The lines a planner DECIDED that this confirmation cannot carry, and why, so the screen can
 * say so and the count on the button agrees with the notice beside it.
 *
 * Adoption mirrored the order's open lines at the time it ran, so a later upload can add a core
 * line with no mirror: its order stays confirmable and that one contribution has no
 * `project_line_id`. Posting an invented id is refused outright, and silently dropping the row
 * would tell a planner they committed something they did not. The fix is a re-sync on the
 * sheet, which is somewhere else entirely - which is exactly why saying nothing would be wrong.
 * The other two reasons are fixed in the editor: a Reserve the board cannot address to a
 * warehouse, and a Buy of a discontinued product with no reason given.
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
   * appear - so naming all of them would be eleven false alarms. The other reasons still name
   * their line: adoption fixes none of them.
   */
  isAdopted = true,
): UnpostableLine[] {
  const unpostable: UnpostableLine[] = [];
  for (const contribution of contributions) {
    if (contribution.sales_order_id !== salesOrderId) continue;
    const built = lineFor(contribution, draft[contribution.key]);
    if (typeof built !== 'string') continue;
    if (built === 'no_mirror' && !isAdopted) continue;
    unpostable.push({ contribution, reason: built });
  }
  return unpostable;
}

/**
 * The lines this press INTENDS to commit, whether or not their mirrors exist yet.
 *
 * On an adopted order this is the body's own length. On one that has not been adopted the body
 * cannot be built at all yet - `project_line_id` is null everywhere until adoption mirrors the
 * open lines - so the count comes from the verdicts instead, and the press adopts before it
 * builds anything. Without this the Confirm on a fresh order would read "Confirm 0 lines" and
 * be disabled, which is exactly the dead end the captain hit. A verdict the body could not
 * carry for any OTHER reason is not counted: adoption does not fix it, and the notice names it.
 */
export function plannedLineCount(
  contributions: BoardContribution[],
  salesOrderId: string,
  draft: BoardDraft,
): number {
  return contributions.filter((contribution) => {
    if (contribution.sales_order_id !== salesOrderId) return false;
    if (contribution.unplannable) return false;
    const built = lineFor(contribution, draft[contribution.key]);
    return built !== null && (typeof built !== 'string' || built === 'no_mirror');
  }).length;
}

/**
 * Whether an amend needs a reason, read over the WHOLE composition.
 *
 * Moving stock the rule proposed takes it away from this line, or from somebody else, and
 * hands it to nobody in particular, so a person has to say why. Accepting the proposal
 * unchanged does not: demanding a reason for agreeing is how a mandatory field becomes a
 * rubber stamp.
 *
 * It looked at the Reserve alone while the Reserve was all a board amendment could change.
 * Now that the editor composes all four kinds, a planner could take 40 out of the Reserve and
 * put 40 into a Borrow - displacing the rule completely - and be asked for nothing.
 *
 * The BASELINE is what the composition is compared against, and it differs by line. On an
 * undecided line it is the engine's proposal, on which a Borrow of any size is an override,
 * because the engine proposes none. On a line an active decision COVERS it is the frozen
 * composition itself: a Borrow decided on the sheet is already the decision, and demanding a
 * reason to re-save it unchanged is the rubber stamp again from the other side.
 */
export function amendNeedsReason(
  contribution: BoardContribution,
  composition: AmendComposition,
): boolean {
  const frozen = contribution.covered ? contribution.decision : null;
  const baseline: AmendComposition = frozen
    ? {
        timely_spo_qty: frozen.timely_spo_qty,
        reserve: frozen.reserve.map((row) => ({ qty: row.qty, warehouse_id: row.warehouse_id })),
        borrow: frozen.borrow.map((row) => ({
          qty: row.qty,
          warehouse_id: row.warehouse_id ?? null,
          donor_project_id: row.donor_project_id ?? null,
        })),
        buy_qty: frozen.buy_qty,
      }
    : proposalBaseline(contribution);

  return (
    !sameRows(baseline.reserve, composition.reserve, (row) => row.warehouse_id ?? '') ||
    toMinor(composition.timely_spo_qty) !== toMinor(baseline.timely_spo_qty) ||
    toMinor(composition.buy_qty) !== toMinor(baseline.buy_qty) ||
    !sameRows(
      baseline.borrow,
      composition.borrow,
      (row) => `${row.warehouse_id ?? ''}|${row.donor_project_id ?? ''}`,
    )
  );
}

/** The four kinds as the editor holds them; the ids are what makes "the same" mean something. */
interface AmendComposition {
  timely_spo_qty: string;
  reserve: { qty: string; warehouse_id?: string | null }[];
  borrow: { qty: string; warehouse_id?: string | null; donor_project_id?: string | null }[];
  buy_qty: string;
}

/**
 * The engine's proposal as a composition: the Reserve per warehouse off the sources (the
 * server's total when it addressed none of them), the incoming cover, the Buy, and no Borrow.
 */
function proposalBaseline(contribution: BoardContribution): AmendComposition {
  const reserve = contribution.sources
    .filter((source) => source.kind === 'reserve')
    .map((source) => ({ qty: source.qty, warehouse_id: source.warehouse_id ?? null }));
  const statedReserve = numberOr(contribution.qty_proposed_reserve, () =>
    sumSources(contribution, 'reserve'),
  );
  return {
    timely_spo_qty: fromMinor(
      numberOr(contribution.qty_proposed_incoming, () => sumSources(contribution, 'timely_spo')),
    ),
    reserve:
      reserve.length > 0 || statedReserve === 0
        ? reserve
        : [{ qty: fromMinor(statedReserve), warehouse_id: null }],
    borrow: [],
    buy_qty: fromMinor(numberOr(contribution.qty_proposed_buy, () => sumSources(contribution, 'buy'))),
  };
}

/**
 * Whether two lists of quantities are the same composition. Compared per key when every row on
 * both sides carries one, so 40 at the pool is not "the same" as 40 at the own location; by
 * total otherwise, which is all an unaddressed row can be compared on. A zero row is nobody's.
 */
function sameRows<T extends { qty: string }>(
  left: T[],
  right: T[],
  keyOf: (row: T) => string,
): boolean {
  const kept = (rows: T[]) => rows.filter((row) => toMinor(row.qty) !== 0);
  const a = kept(left);
  const b = kept(right);
  const addressed = [...a, ...b].every((row) => keyOf(row) !== '' && keyOf(row) !== '|');
  if (!addressed) {
    return sumMinor(a) === sumMinor(b);
  }
  const byKey = (rows: T[]) => {
    const totals = new Map<string, number>();
    for (const row of rows) {
      totals.set(keyOf(row), (totals.get(keyOf(row)) ?? 0) + toMinor(row.qty));
    }
    return totals;
  };
  const mine = byKey(a);
  const theirs = byKey(b);
  if (mine.size !== theirs.size) return false;
  for (const [key, qty] of mine) {
    if (theirs.get(key) !== qty) return false;
  }
  return true;
}

function sumMinor(rows: { qty: string }[]): number {
  return rows.reduce((total, row) => total + toMinor(row.qty), 0);
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
): { cell: string; note: string | null } | null {
  if (cell.rank_separates) return null;
  // A cell that states neither flag was not ranked as one queue: a pivoted cell spans several
  // piles, so it has no single ranking sentence and each line keeps its own score.
  if (cell.rank_separates === undefined && cell.distinct_order_count === undefined) return null;
  // ONE line in the cell still reads "Not ranked" in the Rank column - a flat 0.00 there would
  // claim a ranking nothing computed - but it carries NO sentence (25 August 2026). "Only line
  // in this cell" restated the single row the reader was already looking at, and a sentence
  // that repeats the screen is one more thing to read past on the way to the decision.
  if (cell.contributions.length === 1) return { cell: 'Not ranked', note: null };
  const note =
    (cell.distinct_order_count ?? 0) === 1
      ? 'Same sales order; line order decided which line was served first'
      : 'The active policy separates none of these rows';
  return { cell: 'Not ranked', note };
}

/**
 * The list view's row order: the board's OWN product order, product by product.
 *
 * The grid and the list are two readings of one payload, and the reader toggles between them
 * to find the same line. The grid's vertical axis is `productRows`, which the server sends in
 * its own order; the list was handed `contributions` in the order the demand query returned
 * them, so the same product sat in two different places and the toggle became a re-search.
 *
 * One ordering, and it is the payload's: a line sorts by where its product appears on the
 * grid's axis, then by required date, sales order and line number so the sequence is TOTAL - a
 * partial rule gives a different answer on each render and the two views drift apart again.
 * A product the axis does not name keeps its relative position at the end rather than being
 * dropped; the list is the overview of the WHOLE selection, so it may legitimately hold a line
 * the (windowed) grid does not show.
 */
export function orderByProductRows<T extends { item_code: string; required_date?: string | null; so_number?: string; line_no?: number }>(
  contributions: readonly T[],
  productRows: readonly BoardProductRow[],
): T[] {
  const rank = new Map<string, number>();
  productRows.forEach((row, index) => rank.set(row.item_code, index));
  const after = productRows.length;
  return [...contributions].sort((a, b) => {
    const byProduct = (rank.get(a.item_code) ?? after) - (rank.get(b.item_code) ?? after);
    if (byProduct !== 0) return byProduct;
    if (a.item_code !== b.item_code) return a.item_code.localeCompare(b.item_code);
    // A line nobody dated sorts last within its product, the same way an undated order sorts
    // last on every other listing in this product.
    const byDate = (a.required_date ?? '9999-12-31').localeCompare(b.required_date ?? '9999-12-31');
    if (byDate !== 0) return byDate;
    const byOrder = (a.so_number ?? '').localeCompare(b.so_number ?? '');
    if (byOrder !== 0) return byOrder;
    return (a.line_no ?? 0) - (b.line_no ?? 0);
  });
}
