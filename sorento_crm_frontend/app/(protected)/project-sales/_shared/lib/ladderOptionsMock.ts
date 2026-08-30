import type {
  BoardContribution,
  BoardLadderOption,
  BoardTrailStep,
  PlanningBoard,
} from '../types/fulfilmentPlanning.types';

/**
 * ============================================================================
 * PHASE 1 ONLY - ladder v7.1 options, laid over a real board (S3, AC-S3-11 / AC-S3-14)
 * ============================================================================
 *
 * THIS FILE IS DELETED IN PHASE 2, and its one import line in
 * `services/fulfilmentPlanningService.ts` with it. It exists so the two surfaces AC-S3-14
 * names - the trail popover and the decision panel - can be built and looked at in a browser
 * before `propose_line` returns a single option, which is the whole point of building the
 * frontend first.
 *
 * `NEXT_PUBLIC_LADDER_OPTIONS_MOCK=1` turns it on. OFF, `withLadderOptions` returns the
 * server's board untouched and not one byte of this file reaches a rendered pixel, so it
 * cannot mask a backend that has started answering for real.
 *
 * WHAT IT LAYS OVER, and why it is a layer rather than a whole fixture board: the board this
 * decorates is the REAL one off the lane backend, with the real orders, quantities, locations
 * and ranks. The only invented fields are `options` and `trail` - the two S3 adds - so every
 * state is looked at against the book a planner would actually be reading. A fixture board
 * would also have needed inventing every one of those facts, and would then have proved the
 * table renders against numbers nobody has to believe.
 *
 * FOUR SCENARIOS, cycled over the board's own lines in order, so all five states AC-S3-14 asks
 * for are on one screen: a chosen `use` (A), a step that is not whole (B, C, D), an
 * `order_borrow` carrying its debt month (A, B), a `supply_borrow` at an arrival date with
 * `days_late` above zero (A, B, C), and a Buy at `as_of + lead` (all four).
 *
 * The donor is the plan's own worked example - SO414285 line 4, JEREMY, due 12 Nov 2026 - so
 * the borrow sentence on screen is the one AC-S3-11 states, word for word.
 *
 * Lines the ladder did not walk are left alone: an unplannable line has no options, and a
 * covered one carries a frozen composition rather than a live walk.
 */
export const LADDER_OPTIONS_MOCK =
  process.env.NEXT_PUBLIC_LADDER_OPTIONS_MOCK === '1';

/** The engine's supplier-lead fallback (PLAN section 6 note 5), so Buy lands somewhere real. */
const LEAD_DAYS = 90;
/** How late a borrowed document arrives, in this fixture. Any positive number would do. */
const ARRIVAL_LAG_DAYS = 21;
/** A transfer between bins costs two days (R36). */
const TRANSFER_DAYS = 2;

/** The plan's worked donor (AC-S3-11), named the same way on every line that borrows. */
const DONOR = {
  so_number: 'SO414285',
  line_no: 4,
  agent: 'JEREMY',
  warehouse: 'MWH-IB',
  required_date: '2026-11-12',
  month: '2026-11',
};

/**
 * The server's board with `options` (and the v7.1 trail that explains them) laid on top.
 *
 * Keyed by `BoardContribution.key` and applied to BOTH lists: `PlanningBoard.contributions` is
 * the whole selection and `cells[].contributions` is what a cell holds, and they are separate
 * objects over the wire. Decorating only one would leave the popover and the panel disagreeing
 * about the same line, which is exactly the bug this feature exists to stop.
 */
export function withLadderOptions(board: PlanningBoard): PlanningBoard {
  if (!LADDER_OPTIONS_MOCK) return board;
  // Defensive because it is a decorator over a live payload: a board that arrived without
  // either list is a board this has nothing to say about, and throwing here would look like
  // the board endpoint itself had failed.
  if (!Array.isArray(board?.contributions)) return board;

  const decorated = new Map<string, BoardContribution>();
  board.contributions.forEach((contribution, index) => {
    if (!walked(contribution)) return;
    decorated.set(contribution.key, decorate(contribution, board.as_of, index));
  });

  return {
    ...board,
    contributions: board.contributions.map(
      (contribution) => decorated.get(contribution.key) ?? contribution,
    ),
    cells: (board.cells ?? []).map((cell) => ({
      ...cell,
      contributions: (cell.contributions ?? []).map(
        (contribution) => decorated.get(contribution.key) ?? contribution,
      ),
    })),
  };
}

/** Was a ladder walked for this line at all? Only those have options to state. */
function walked(contribution: BoardContribution): boolean {
  return !contribution.unplannable && !contribution.covered;
}

function decorate(
  contribution: BoardContribution,
  asOf: string,
  index: number,
): BoardContribution {
  const scenario = index % 4;
  const required = contribution.required_date ?? asOf;
  const qty = contribution.qty || '0';
  const location = contribution.fulfilment_location ?? 'the line location';

  const transferDate = addDays(asOf, TRANSFER_DAYS);
  const arrival = addDays(later(required, asOf), ARRIVAL_LAG_DAYS);
  const buyDate = addDays(asOf, LEAD_DAYS);

  // Which step the engine proposed: the FIRST whole one, exactly as the ladder chooses.
  const chosen: BoardLadderOption['step'] =
    scenario === 0
      ? 'use'
      : scenario === 1
        ? 'order_borrow'
        : scenario === 2
          ? 'supply_borrow'
          : 'buy';

  const useWhole = scenario === 0;
  const orderBorrowWhole = scenario === 0 || scenario === 1;
  const supplyBorrowWhole = scenario !== 3;

  const options: BoardLadderOption[] = [
    {
      step: 'use',
      label: useWhole
        ? `Use ${qty} at ${location}`
        : `Use what is free at ${location}`,
      whole: useWhole,
      fulfil_date: useWhole ? asOf : null,
      days_late: useWhole ? 0 : null,
      chosen: chosen === 'use',
    },
    {
      step: 'order_borrow',
      label: orderBorrowWhole
        ? `Borrow ${qty} on hand from ${DONOR.so_number}`
        : `Borrow on hand from a later order`,
      whole: orderBorrowWhole,
      fulfil_date: orderBorrowWhole ? transferDate : null,
      days_late: orderBorrowWhole ? daysLate(required, transferDate) : null,
      debt_so_number: orderBorrowWhole ? DONOR.so_number : null,
      debt_month: orderBorrowWhole ? DONOR.month : null,
      chosen: chosen === 'order_borrow',
    },
    {
      step: 'supply_borrow',
      label: supplyBorrowWhole
        ? `Borrow ${qty} arriving on SPO-2026/08-0061`
        : 'Borrow the supply a later order holds',
      whole: supplyBorrowWhole,
      fulfil_date: supplyBorrowWhole ? arrival : null,
      days_late: supplyBorrowWhole ? daysLate(required, arrival) : null,
      debt_so_number: supplyBorrowWhole ? DONOR.so_number : null,
      debt_month: supplyBorrowWhole ? DONOR.month : null,
      chosen: chosen === 'supply_borrow',
    },
    {
      // The pool is never whole in this fixture: it is the step that shows what a No looks
      // like on every scenario, which is the row the reader has to be able to skip past.
      step: 'pool',
      label: 'Take from the pool',
      whole: false,
      fulfil_date: null,
      days_late: null,
      chosen: false,
    },
    {
      step: 'buy',
      label: `Buy ${qty}`,
      whole: true,
      fulfil_date: buyDate,
      days_late: daysLate(required, buyDate),
      chosen: chosen === 'buy',
    },
  ];

  return { ...contribution, options, trail: trailFor(options, qty, location) };
}

/**
 * The five questions of ladder v7.1, in AC-S3-11's order and words.
 *
 * The engine writes these in Phase 2 - `question`, `took`, `from` and `why` are all the
 * SERVER's sentences, never assembled on the client (see `BoardTrailStep.why`). The fixture
 * writes them here only so the popover can be looked at in the order the AC states, and it
 * goes with the rest of this file in Phase 2.
 */
function trailFor(
  options: BoardLadderOption[],
  qty: string,
  location: string,
): BoardTrailStep[] {
  const by = (step: BoardLadderOption['step']) =>
    options.find((option) => option.step === step)!;
  const use = by('use');
  const orderBorrow = by('order_borrow');
  const supplyBorrow = by('supply_borrow');
  const buy = by('buy');

  return [
    {
      step: 1,
      kind: 'own',
      question: 'Can we use our locations?',
      answer: use.chosen ? 'yes' : 'no',
      took: use.chosen ? qty : '0',
      from: use.chosen ? location : null,
      location: use.chosen ? location : null,
      why: use.chosen
        ? `Free at ${location} by this line's date, so nobody is owed anything.`
        : `Nothing is free at ${location} by this line's date once the earlier-dated lines of the group have taken theirs.`,
    },
    {
      step: 2,
      kind: 'order_borrow',
      question: 'Can we borrow on hand from a later order?',
      answer: orderBorrow.chosen ? 'yes' : 'no',
      took: orderBorrow.chosen ? qty : '0',
      // NULL ON A NO, as `BoardTrailStep.from` documents: the column says where the line TOOK
      // from, and naming a warehouse beside a 0 reads as stock that moved and did not.
      from: orderBorrow.chosen ? DONOR.warehouse : null,
      // The sentence AC-S3-11 states, word for word: what is borrowed, where it is held, whose
      // order it is taken from, when that order is due, and where its debt lands.
      why: orderBorrow.whole
        ? `Borrow ${qty} on hand at ${DONOR.warehouse} from ${DONOR.so_number} line ${DONOR.line_no} (${DONOR.agent}, due 12 Nov 2026); its debt lands in Nov 2026`
        : 'No later order holds enough on hand to cover the whole unit.',
    },
    {
      step: 3,
      kind: 'supply_borrow',
      question: 'Can we borrow incoming from a later order?',
      answer: supplyBorrow.chosen ? 'yes' : 'no',
      took: supplyBorrow.chosen ? qty : '0',
      from: supplyBorrow.chosen ? DONOR.warehouse : null,
      why: supplyBorrow.whole
        ? `Borrow ${qty} arriving ${formatted(supplyBorrow.fulfil_date)} (SPO-2026/08-0061) from ${DONOR.so_number} line ${DONOR.line_no}; its debt lands in Nov 2026`
        : 'No single document arriving in time covers the whole unit.',
    },
    {
      step: 4,
      kind: 'pool',
      question: 'Can we take from the pool?',
      answer: 'no',
      took: '0',
      from: null,
      why: "The pool's own book leaves nothing free for this line by its date.",
    },
    {
      step: 5,
      kind: 'buy',
      question: 'Buy',
      answer: buy.chosen ? 'yes' : 'no',
      took: buy.chosen ? qty : '0',
      from: null,
      why: buy.chosen
        ? `Nothing above covers the whole unit, so it is bought; a fresh order lands about ${formatted(buy.fulfil_date)}.`
        : 'Not needed: the unit is covered above.',
    },
  ];
}

// ------------------------------------------------------------------ date maths
// Plain UTC arithmetic on `YYYY-MM-DD`: no timezone is involved, because a required date and
// an arrival are civil dates, not instants.

function addDays(date: string, days: number): string {
  const at = new Date(`${date.slice(0, 10)}T00:00:00Z`);
  at.setUTCDate(at.getUTCDate() + days);
  return at.toISOString().slice(0, 10);
}

function later(a: string, b: string): string {
  return a.slice(0, 10) >= b.slice(0, 10) ? a.slice(0, 10) : b.slice(0, 10);
}

/** Never negative: early is not "minus six days late", it is on time. */
function daysLate(required: string, fulfil: string): number {
  const from = Date.parse(`${required.slice(0, 10)}T00:00:00Z`);
  const to = Date.parse(`${fulfil.slice(0, 10)}T00:00:00Z`);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return 0;
  return Math.max(0, Math.round((to - from) / 86_400_000));
}

/** `2026-09-15` -> `15 Sep 2026`, for the server sentences this fixture stands in for. */
function formatted(date?: string | null): string {
  if (!date) return 'an unknown date';
  const [year, month, day] = date.slice(0, 10).split('-');
  const names = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  return `${Number(day)} ${names[Number(month) - 1] ?? month} ${year}`;
}
