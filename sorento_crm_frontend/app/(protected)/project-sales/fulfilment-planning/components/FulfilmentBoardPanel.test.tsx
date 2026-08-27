/**
 * The multi-order planning board on screen (PLAN section 13).
 *
 * What is worth pinning is the honesty of the thing rather than its pixels: Overdue is first
 * and No date is last, a cell that draws on two locations says both, a line whose sales order
 * states no location is visible AND blocks its order, and above all the per-order "N of M lines
 * decided" counter gates Confirm with its reason showing. That counter is the whole reason the
 * ownership question in 13.4 is a question, so a board that smoothed it over would be
 * misrepresenting the design.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: (...args: unknown[]) => routerReplace(...args) }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getPlanningBoard = vi.fn();
const confirmSupply = vi.fn();
const adoptSalesOrder = vi.fn();
const confirmMany = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: (...args: unknown[]) => adoptSalesOrder(...args),
  getSupply: vi.fn(),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  confirmMany: (...args: unknown[]) => confirmMany(...args),
  // Declared INSIDE the factory: `vi.mock` is hoisted above every top-level binding, so a
  // class declared outside it is not initialised yet when the factory runs.
  ConfirmSupplyError: class ConfirmSupplyError extends Error {
    readonly failingLines: {
      line_no?: number | null;
      item_code?: string | null;
      reason: string;
    }[];
    constructor(
      message: string,
      failingLines: { line_no?: number | null; item_code?: string | null; reason: string }[] = [],
    ) {
      super(message);
      this.name = 'ConfirmSupplyError';
      this.failingLines = failingLines;
    }
  },
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    id,
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
    id?: string;
  }) => (
    <select
      aria-label={id ?? 'granularity'}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {(options ?? []).map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

import { ConfirmSupplyError } from '../../_shared/services/fulfilmentPlanningService';
import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import { buildBoard, type BoardDemandLine } from '../../_shared/lib/__testsupport__/boardFixture';
import type {
  BoardContribution,
  BoardGranularity,
  BoardPolicy,
  PlanningBoard,
} from '../../_shared/types/fulfilmentPlanning.types';

const TODAY = '2026-08-18';

function demand(overrides: Partial<BoardDemandLine> = {}): BoardDemandLine {
  return {
    sales_order_id: 'so-a',
    so_number: 'SO403340',
    customer_name: 'SETIA-WOOD INDUSTRIES SDN BHD (PROJECT)',
    project_label: 'SETIA-WOOD INDUSTRIES/100U DSTH (DIMINA) @ SETIA',
    line_no: 1,
    item_code: 'WESERP10B',
    qty: '100',
    required_date: '2026-09-04',
    fulfilment_location: 'BRW-BB',
    priority: null,
    ...overrides,
  };
}

function boardOf(
  lines: BoardDemandLine[],
  freeStock: Record<string, string> = {},
  granularity: BoardGranularity = 'week',
) {
  return buildBoard(lines, { today: TODAY, freeStock, granularity });
}

/**
 * Applies `transform` to every matching contribution across BOTH `cells[].contributions` and
 * the board's own top-level `contributions` (the review finding's fix): Confirm, the previews,
 * the unpostable-line detection and Approve all all read the top-level list now, never the
 * cells, so a test simulating a server-stated fact on one contribution has to state it on both
 * copies or the mutation is invisible to half the component.
 */
function withContribution(
  board: PlanningBoard,
  match: (entry: BoardContribution) => boolean,
  transform: (entry: BoardContribution) => BoardContribution,
): PlanningBoard {
  const apply = (entry: BoardContribution) => (match(entry) ? transform(entry) : entry);
  return {
    ...board,
    cells: board.cells.map((cell) => ({ ...cell, contributions: cell.contributions.map(apply) })),
    contributions: board.contributions.map(apply),
  };
}

function renderPanel(soNumbers = ['SO403340', 'SO398322'], onBack: () => void = vi.fn()) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} onBack={onBack} />
    </QueryClientProvider>,
  );
}

/**
 * The dialog carries two buttons named Close: Radix's own corner dismiss and the footer one.
 * The footer is the last in document order, and naming that here keeps the ambiguity in one
 * place rather than in every test that decides a cell.
 */
function closeDialog() {
  const buttons = screen.getAllByRole('button', { name: 'Close' });
  fireEvent.click(buttons[buttons.length - 1]);
}

beforeEach(() => {
  vi.clearAllMocks();
  currentSearchParams = new URLSearchParams('');
});

/**
 * Title left, actions right (captain, with a screenshot of Back overlapping the title).
 *
 * `flex items-center justify-between` does not wrap, so a long title and a control row
 * collide at narrow widths and push the whole page sideways - the exact failure the
 * responsive-header rule in CLAUDE.md exists to prevent.
 */
describe('FulfilmentBoardPanel: the header', () => {
  it('puts Back to sales orders in the actions on the right, after the granularity control', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const actions = screen.getByTestId('board-header-actions');
    const back = within(actions).getByRole('button', { name: 'Back to sales orders' });
    const granularity = within(actions).getByLabelText('granularity');
    expect(back.compareDocumentPosition(granularity)).toBe(Node.DOCUMENT_POSITION_PRECEDING);
  });

  it('still calls back, which is now the sales-order list', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));
    const onBack = vi.fn();

    renderPanel(['SO403340'], onBack);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'Back to sales orders' }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('lets the header wrap instead of overlapping the title', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const header = screen.getByTestId('board-header');
    expect(header.className).toContain('flex-col');
    expect(header.className).toContain('sm:flex-row');
    expect(screen.getByTestId('board-header-title').className).toContain('min-w-0');
    expect(screen.getByTestId('board-header-actions').className).toContain('flex-wrap');
  });
});

describe('FulfilmentBoardPanel: the axes', () => {
  it('orders the buckets chronologically and pins No date last, with no Overdue column at all', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, required_date: '2026-09-04' }),
        demand({ line_no: 2, required_date: '2022-07-03' }),
        demand({ line_no: 3, required_date: null, fulfilment_location: null }),
      ]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const headers = within(matrix)
      .getAllByRole('columnheader')
      .map((node) => node.textContent ?? '');
    expect(headers[0]).toBe('Product');
    expect(headers[1]).toContain('27 Jun 2022');
    expect(headers[2]).toContain('31 Aug 2026');
    expect(headers[headers.length - 1]).toContain('No date');
    expect(headers.some((header) => header.includes('Overdue'))).toBe(false);
  });

  /**
   * The captain, verbatim: "what does w/c 2 Nov 2026 mean? what does w/c mean?" - and then,
   * on being offered replacements, "just remove it". Having to ask IS the verdict: "w/c" is
   * week-commencing, a scheduling abbreviation, and the granularity control already says the
   * board is by week, so the column has nothing left to restate.
   */
  it('heads a week column with the date alone, with no abbreviation to decode', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand({ required_date: '2026-11-04' })]));

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const header = matrix.querySelector('[data-bucket="2026-11-02"]');
    expect(header?.textContent).toBe('2 Nov 2026');
  });

  it('strips the abbreviation from the cell dialog’s title too', async () => {
    const board = boardOf([demand({ required_date: '2026-11-04', item_code: 'WESERP10B' })]);
    getPlanningBoard.mockResolvedValue({
      ...board,
      dateBuckets: board.dateBuckets.map((bucket) => ({
        ...bucket,
        label: `w/c ${bucket.label}`,
      })),
    });

    renderPanel(['SO403340']);
    fireEvent.click(
      await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }),
    );

    expect(await screen.findByText('WESERP10B · 2 Nov 2026')).toBeInTheDocument();
  });

  it('strips the abbreviation even when the server is still sending it', async () => {
    // Bridge: the label is formatted server-side, so until that lane lands the client must not
    // put jargon on screen. Idempotent - it does nothing once the server stops sending it.
    const board = boardOf([demand({ required_date: '2026-11-04' })]);
    getPlanningBoard.mockResolvedValue({
      ...board,
      dateBuckets: board.dateBuckets.map((bucket) => ({
        ...bucket,
        label: `w/c ${bucket.label}`,
      })),
    });

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    expect(matrix.querySelector('[data-bucket="2026-11-02"]')?.textContent).toBe('2 Nov 2026');
  });

  /**
   * The captain's instruction, and the thing that made this a bug rather than a preference:
   * a 2022 date is its own column, tinted, and its quantity is NOT summed into anything else.
   */
  it('gives a bucket dated years back its own column, tinted, outside any aggregate', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, qty: '40', required_date: '2022-07-03' }),
        demand({ line_no: 2, qty: '100', required_date: '2026-09-04' }),
      ]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const past = matrix.querySelector('[data-bucket="2022-06-27"]');
    expect(past).not.toBeNull();
    expect(past?.getAttribute('data-past')).toBe('true');
    expect(matrix.querySelector('[data-bucket="2026-08-31"]')?.getAttribute('data-past')).toBe(
      'false',
    );
    // Its quantity stands alone in its own cell rather than being rolled into a later one.
    expect(
      within(matrix).getByRole('button', { name: /WESERP10B, 40 across 1 sales order/ }),
    ).toBeInTheDocument();
    expect(
      within(matrix).getByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }),
    ).toBeInTheDocument();
  });

  /**
   * The two `is_past` flags answer different questions, and this is the one that catches it:
   * a line due two days ago sits in the week that CONTAINS as_of, so its bucket is not past
   * (some of that week is still to come) while the line certainly is. Counting off the bucket
   * would report zero late lines on a board full of them.
   */
  it('counts late LINES, not late buckets, so a line due this week still counts', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, required_date: '2026-08-17' }),
        demand({ line_no: 2, required_date: '2026-08-20' }),
      ]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    // One bucket, the week of as_of, and it is NOT tinted.
    expect(matrix.querySelector('[data-bucket="2026-08-17"]')?.getAttribute('data-past')).toBe(
      'false',
    );
    // AC-C5 (26 August 2026): the banner that used to say so is gone. What remains is the
    // per-bucket tint, which is what the header already announces.
    expect(screen.queryByText(/lines are already past their delivery date/)).toBeNull();
  });

  it('renders the products down the side', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([demand({ item_code: 'WESERP10B' }), demand({ item_code: 'TPE-9204', line_no: 2 })]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const rows = within(matrix)
      .getAllByRole('rowheader')
      .map((node) => node.textContent);
    expect(rows).toEqual(['TPE-9204', 'WESERP10B']);
  });
});

describe('FulfilmentBoardPanel: the cells', () => {
  it('aggregates several orders into one cell and says how many', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, qty: '100' }),
        demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, qty: '74' }),
      ]),
    );

    renderPanel();

    const cell = await screen.findByRole('button', { name: /WESERP10B, 174 across 2 sales orders/ });
    expect(within(cell).getByText('174')).toBeInTheDocument();
    expect(within(cell).getByText('2 orders')).toBeInTheDocument();
  });

  it('shows the source strip when one cell draws on several locations (13.7)', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, qty: '22', fulfilment_location: 'BRW-BB' }),
        demand({ line_no: 2, qty: '21', fulfilment_location: 'BRW' }),
      ]),
    );

    renderPanel();

    expect(await screen.findByTitle('BRW-BB 22 · BRW 21')).toBeInTheDocument();
  });

  it('marks a cell that carries a line with no location', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, qty: '24', fulfilment_location: null }),
        demand({ line_no: 2, qty: '10' }),
      ]),
    );

    renderPanel();

    expect(await screen.findByText('1 needs a location')).toBeInTheDocument();
  });

  it('marks a cell whose stock an earlier-dated line already took', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf(
        [
          demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, qty: '100', required_date: '2026-09-04' }),
          demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2, qty: '100', required_date: '2026-09-02' }),
        ],
        { 'WESERP10B|BRW-BB': '100' },
      ),
    );

    renderPanel();

    expect(await screen.findByText('1 contested')).toBeInTheDocument();
  });

  it('leaves a product-and-date nobody owes blank, because a blank cell is not a zero', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ item_code: 'WESERP10B', line_no: 1, required_date: '2026-09-04' }),
        demand({ item_code: 'TPE-9204', line_no: 2, required_date: '2026-12-01' }),
      ]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const empty = matrix.querySelector('[data-cell="TPE-9204|2026-08-31"]');
    expect(empty).not.toBeNull();
    expect(empty?.textContent).toBe('');
    expect(within(matrix).getAllByRole('button').length).toBe(2);
  });
});

describe('FulfilmentBoardPanel: the commit rail (13.4)', () => {
  it('shows the decided counter per order, as information', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1 }),
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 2, required_date: '2026-12-01' }),
        demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 3 }),
      ]),
    );

    renderPanel();

    expect(await screen.findByText('0 of 2 lines decided')).toBeInTheDocument();
    expect(screen.getByText('0 of 1 lines decided')).toBeInTheDocument();
  });

  it('offers nothing to confirm before anything is decided, and says so', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1 })]),
    );

    renderPanel(['SO403340']);

    expect(await screen.findByText('Nothing decided yet on this order.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm this order' })).toBeDisabled();
  });

  it('ENABLES Confirm on a partial decision, and states what it leaves behind', async () => {
    // The captain's decision (13.4), and the reason for it: undecided lines must keep flowing
    // to reorder planning, so a partly-decided order must be committable.
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1, item_code: 'WESERP10B' }),
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 2, item_code: 'TPE-9204' }),
      ]),
    );

    renderPanel(['SO403340']);

    fireEvent.click(await screen.findByRole('button', { name: /TPE-9204, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() => expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument());
    expect(
      screen.getByText('Confirms 1, leaves 1 undecided for reorder planning.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm 1 line' })).toBeEnabled();
  });

  it('says it confirms everything once the whole order is decided', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1 })]),
    );

    renderPanel(['SO403340']);

    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() => expect(screen.getByText('Confirms all 1.')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: 'Confirm this order' })).toBeEnabled();
  });

  it('names the lines that can never be decided here inside what is left behind', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ sales_order_id: 'so-a', so_number: 'SO366992', line_no: 1, item_code: 'WESERP10B' }),
        demand({
          sales_order_id: 'so-a',
          so_number: 'SO366992',
          line_no: 2,
          item_code: 'TPE-9204',
          fulfilment_location: null,
        }),
      ]),
    );

    renderPanel(['SO366992']);

    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() =>
      expect(
        screen.getByText(
          'Confirms 1, leaves 1 undecided for reorder planning (1 of them need a location on the sales order).',
        ),
      ).toBeInTheDocument(),
    );
  });
});

/**
 * The counter the captain asked to see, at the granularity that used to lie about it.
 *
 * The standings were built from the cells on screen, so at day granularity a forty-line order
 * read "3 of 3 lines decided" and Confirm promised to leave nothing behind. The server's
 * `orders[]` is selection-scoped; only the verdicts are the client's.
 */
describe('FulfilmentBoardPanel: the commit rail is selection-scoped, not window-scoped', () => {
  /** Three lines inside the first day window, thirty-seven far outside it. */
  function fortyLines() {
    const inside = Array.from({ length: 3 }, (_unused, index) =>
      demand({ line_no: index + 1, item_code: `IN-${index}`, required_date: '2026-09-04' }),
    );
    const outside = Array.from({ length: 37 }, (_unused, index) =>
      demand({ line_no: 100 + index, item_code: `OUT-${index}`, required_date: '2028-01-04' }),
    );
    return [...inside, ...outside];
  }

  it('counts all forty lines at day granularity, where only three are on screen', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation((_orders: unknown, granularity: BoardGranularity) =>
      Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.getByText('0 of 40 lines decided')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'day' } });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'day', false, {}),
    );

    // The window shows three of the forty; the counter must still say forty.
    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    expect(within(matrix).getAllByRole('button')).toHaveLength(3);
    await waitFor(() => expect(screen.getByText('0 of 40 lines decided')).toBeInTheDocument());
  });

  it('states what a decision leaves behind against the whole order, not the window', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation((_orders: unknown, granularity: BoardGranularity) =>
      Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'day' } });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'day', false, {}),
    );

    fireEvent.click(await screen.findByRole('button', { name: /IN-0, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() =>
      expect(
        screen.getByText('Confirms 1, leaves 39 undecided for reorder planning.'),
      ).toBeInTheDocument(),
    );
  });

  it('keeps a verdict counted after the window scrolls past the cell it was made on', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation((_orders: unknown, granularity: BoardGranularity) =>
      Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Decide a line that only the WEEK board shows...
    fireEvent.click(
      await screen.findByRole('button', { name: /OUT-0, 100 across 1 sales order/ }),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    await waitFor(() => expect(screen.getByText('1 of 40 lines decided')).toBeInTheDocument());

    // ...then move to a window that does not contain it. The verdict is still the planner's.
    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'day' } });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'day', false, {}),
    );
    await waitFor(() => expect(screen.getByText('1 of 40 lines decided')).toBeInTheDocument());
  });
});

/**
 * The ranking policy is NOT stated at the top of the board (13.5, amended 18 August).
 *
 * The banner named the rule and listed its weights above every board, and the captain's verdict
 * was "this text is not needed at the top". It was answering a question nobody had asked, in the
 * place where the columns and the grid have to be. The name survives where somebody IS asking -
 * above the factor table in the rank popover - so nothing is lost, it has simply moved to the
 * moment it is wanted.
 */
describe('FulfilmentBoardPanel: no ranking banner at the top (13.5)', () => {
  /** A board with the policy the server actually sends, flag and all. */
  function boardWithPolicy(policy: Partial<BoardPolicy>) {
    const board = boardOf([demand()]);
    return { ...board, policy: { ...board.policy, ...policy } };
  }

  it('does not name the policy above the board', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText("Today's rule (PO document sequence)")).not.toBeInTheDocument();
    expect(screen.queryByText(/Ranked by/)).not.toBeInTheDocument();
  });

  it('does not print the weights above the board either', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({
        name: 'Fulfilment board preview',
        factors: { need_by_date: 3, document_age: 1 },
        discriminates_nothing: false,
      }),
    );

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText('Delivery date 3 · Order date 1')).not.toBeInTheDocument();
  });

  /**
   * The flatness sentence goes with it. It was written when the live policy weighted only
   * `po_document_sequence` and ranked nothing at all; the fair policy is live now and STILL
   * reports `discriminates_nothing` on a single-order board, because customer, order date and
   * demand class are constant across one order. So the sentence fired on healthy boards, and a
   * warning that is usually wrong teaches people to ignore warnings. What a cell could not
   * separate is still said inside the cell, by `rankingNote`, where it is about those rows.
   */
  it('does not warn that the ranking is flat, even when the server says it is', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({
        name: 'Weighted but useless here',
        factors: { demand_class: 3, need_by_date: 0 },
        discriminates_nothing: true,
      }),
    );

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/the ranking is flat/)).not.toBeInTheDocument();
  });

  it('carries no preview controls at all, in either direction', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({ name: 'Fulfilment board preview', is_preview: true }),
    );

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText('Preview, not live')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Back to the live policy' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Preview a fairer weighting' }),
    ).not.toBeInTheDocument();
  });
});

describe('FulfilmentBoardPanel: the calendar control (13.3)', () => {
  it('offers day, week and month', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();

    const select = await screen.findByLabelText('granularity');
    expect(within(select).getByRole('option', { name: 'By day' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'By week' })).toBeInTheDocument();
    expect(within(select).getByRole('option', { name: 'By month' })).toBeInTheDocument();
  });

  it('asks the service for the granularity the planner chose', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'month' } });

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'month', false, {}),
    );
  });

  /** Deviation 7: the day view scrolls a 30-day window, and the server is told which one. */
  it('offers a window to scroll only at day granularity, and sends it', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByRole('button', { name: 'Later days' })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'day' } });
    // Wait for the day board to land before scrolling: the window is anchored on the board's
    // own first dated bucket, so scrolling a board that has not arrived anchors on nothing.
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'day', false, {}),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        expect.objectContaining({ dayWindow: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/) }),
      ),
    );
  });

  /**
   * The step is the contract's thirty days, and the anchor is the window the planner asked
   * for. Stepping by the dated columns that came back skipped or re-showed days whenever the
   * server sent fewer than thirty, and a window with no dated column at all could not move.
   */
  it('steps by thirty days even when the server sent fewer dated columns', async () => {
    const dayBoard = boardOf([demand({ required_date: '2026-09-04' })], {}, 'day');
    getPlanningBoard.mockResolvedValue({
      ...dayBoard,
      dateBuckets: dayBoard.dateBuckets.filter((bucket) => bucket.kind === 'dated').slice(0, 5),
    });
    currentSearchParams = new URLSearchParams('granularity=day');

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    const first = dayBoard.dateBuckets.find((bucket) => bucket.kind === 'dated')?.start;
    expect(first).toBe('2026-09-04');

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(['SO403340'], 'day', false, {
        dayWindow: '2026-10-04',
      }),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(['SO403340'], 'day', false, {
        dayWindow: '2026-11-03',
      }),
    );
  });

  it('still moves off a window with no dated column in it', async () => {
    const dayBoard = boardOf([demand({ required_date: '2026-09-04' })], {}, 'day');
    getPlanningBoard.mockResolvedValue(dayBoard);
    currentSearchParams = new URLSearchParams('granularity=day');

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(['SO403340'], 'day', false, {
        dayWindow: '2026-10-04',
      }),
    );

    // The next window has nothing owed in it: no cells, no dated columns.
    getPlanningBoard.mockResolvedValue({ ...dayBoard, dateBuckets: [], cells: [] });
    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(['SO403340'], 'day', false, {
        dayWindow: '2026-11-03',
      }),
    );
    await screen.findByText('Nothing is outstanding in these dates');

    fireEvent.click(screen.getByRole('button', { name: 'Earlier days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(['SO403340'], 'day', false, {
        dayWindow: '2026-10-04',
      }),
    );
  });

  it('asks the server for the live policy, the preview offer having been retired', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // The what-if existed to show a fair weighting before one was switched on. It is now the
    // live one, so every board is fetched against the live policy and nothing offers to
    // preview it against itself.
    expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'week', false, {});
    expect(
      screen.queryByRole('button', { name: 'Preview a fairer weighting' }),
    ).not.toBeInTheDocument();
  });
});

describe('FulfilmentBoardPanel: states', () => {
  it('reports a failure instead of an empty grid', async () => {
    getPlanningBoard.mockRejectedValue(new Error('Backend is down'));

    renderPanel();

    expect(await screen.findByText('The planning board could not be loaded')).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('says so when the selection owes nothing plannable', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([]));

    renderPanel();

    expect(
      await screen.findByText('Nothing is outstanding on these sales orders that can be planned'),
    ).toBeInTheDocument();
  });

  /**
   * The same window-scoped mistake as the banner, in the emptiest possible form: a day window
   * scrolled to a stretch nobody owes has no cells, and "these orders owe nothing" is then a
   * flat contradiction of the 161 lines the selection is holding.
   */
  it('does not call the selection empty when the window is merely showing nothing', async () => {
    const board = boardOf([demand()]);
    getPlanningBoard.mockResolvedValue({
      ...board,
      granularity: 'day',
      cells: [],
      line_count: 161,
      past_line_count: 130,
    });

    renderPanel();

    expect(await screen.findByText('Nothing is outstanding in these dates')).toBeInTheDocument();
    expect(
      screen.queryByText('These sales orders owe nothing that can be planned'),
    ).not.toBeInTheDocument();
  });

  it('does not flash an empty or error state while loading', () => {
    getPlanningBoard.mockReturnValue(new Promise(() => {}));

    renderPanel();

    expect(
      screen.queryByText('These sales orders owe nothing that can be planned'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('The planning board could not be loaded')).not.toBeInTheDocument();
  });
});

/**
 * Confirm, which the captain asked about as a question: "so now when i click the confirm 8
 * lines, it won't work and won't flow to order inquiries isit?" It did not - the button had no
 * onClick at all. It posts to the SAME per-order endpoint the sheet uses (13.4: the board is a
 * lens, and grows no second write path).
 *
 * The two things worth pinning hardest are what happens when it goes wrong: a refusal must not
 * cost the planner the work they did, and it must say which lines were refused and why.
 */
describe('FulfilmentBoardPanel: Confirm actually confirms', () => {
  async function decideFirstCell() {
    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    await waitFor(() => expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument());
  }

  function twoLineOrder() {
    return boardOf([
      demand({ line_no: 1, item_code: 'WESERP10B' }),
      demand({ line_no: 2, item_code: 'TPE-9204' }),
    ]);
  }

  it('posts the decided lines to the order’s own planning record', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    renderPanel(['SO403340']);
    await decideFirstCell();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    await waitFor(() => expect(confirmSupply).toHaveBeenCalledTimes(1));
    const [psoId, body] = confirmSupply.mock.calls[0];
    expect(psoId).toBe('pso-so-a');
    expect(body.lines).toHaveLength(1);
    expect(body.lines[0].project_line_id).toBe('pl-so-a-1');
  });

  it('clears the confirmed lines from the draft and refetches the board', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    renderPanel(['SO403340']);
    await decideFirstCell();
    const boardCallsBefore = getPlanningBoard.mock.calls.length;

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    // The verdict is spent: it is in the database now, not in the draft.
    await waitFor(() => expect(screen.getByText('0 of 2 lines decided')).toBeInTheDocument());
    await waitFor(() =>
      expect(getPlanningBoard.mock.calls.length).toBeGreaterThan(boardCallsBefore),
    );
  });

  it('keeps the draft and names the refused lines when the server refuses', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmSupply.mockRejectedValue(
      new ConfirmSupplyError('The sales order moved on underneath this plan.', [
        { line_no: 1, item_code: 'WESERP10B', reason: 'Only 40 free at BRW-BB now.' },
      ]),
    );

    renderPanel(['SO403340']);
    await decideFirstCell();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    expect(await screen.findByText('Line 1, WESERP10B: Only 40 free at BRW-BB now.')).toBeInTheDocument();
    // The planner does not lose their work to a refusal.
    expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument();
  });

  /**
   * Where the confirmed Buy rows go, and what still does not happen.
   *
   * This sentence used to say "on the sales order itself" and warn that an adopted order was
   * absent from the Order Inquiry list, because that list was project-scoped. A cross-project
   * Order Inquiries page now carries adopted orders' rows, so the warning is spent and the
   * destination is a real place to send somebody.
   */
  it('sends the planner to Order Inquiries, where the rows now actually appear', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    const link = screen.getByRole('link', { name: 'Order Inquiries' });
    expect(link).toHaveAttribute('href', '/project-sales/order-inquiries');
    expect(screen.getByText(/confirmed Buy rows go to/)).toBeInTheDocument();
    // The old caveat is gone with the reason for it.
    expect(screen.queryByText(/on the sales order itself/)).not.toBeInTheDocument();
  });

  it('keeps the commit header to one hint, not a paragraph teaching the feature', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/keeps flowing to reorder planning/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raises no purchasing task/)).not.toBeInTheDocument();
    expect(screen.queryByText(/grouped by delivery month/)).not.toBeInTheDocument();
  });

  /**
   * Adoption mirrored the order's open lines when it ran, so a later upload can add a core line
   * with no mirror. The order is still confirmable; that line is not, and the planner may well
   * have approved it - so it is NAMED rather than silently dropped.
   */
  it('names a decided line that has no mirror, and does not count it in the Confirm', async () => {
    const board = twoLineOrder();
    getPlanningBoard.mockResolvedValue(
      withContribution(
        board,
        (entry) => entry.item_code === 'TPE-9204',
        (entry) => ({ ...entry, project_line_id: null }),
      ),
    );
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    renderPanel(['SO403340']);

    // Decide BOTH lines, including the one with no mirror.
    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    fireEvent.click(await screen.findByRole('button', { name: /TPE-9204, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() => expect(screen.getByText('2 of 2 lines decided')).toBeInTheDocument());
    // Two decided, but only one can be posted, and the button says the number it will post.
    expect(
      await screen.findByText(
        'TPE-9204 line 2 is not on the planning record yet, so this confirmation leaves it out. Re-sync the sales order to add it.',
      ),
    ).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Confirm 1 line' });

    fireEvent.click(confirm);
    await waitFor(() => expect(confirmSupply).toHaveBeenCalledTimes(1));
    expect(confirmSupply.mock.calls[0][1].lines).toHaveLength(1);
  });

  /**
   * The other two ways a decided line cannot be posted used to be SILENT: the body left the
   * line out and the button said "Confirm 7 lines" beside eight verdicts, with nothing on the
   * rail saying which one was missing or why. Both are named now, and the count agrees.
   */
  it('names a decided line whose Reserve the board cannot address, and does not count it', async () => {
    const board = twoLineOrder();
    getPlanningBoard.mockResolvedValue(
      withContribution(
        board,
        (entry) => entry.item_code === 'TPE-9204',
        (entry) => ({
          ...entry,
          qty_proposed_reserve: '100',
          qty_proposed_buy: '0',
          sources: [
            { kind: 'reserve' as const, qty: '100', location: 'BRW-BB', reason: 'Covered.' },
          ],
        }),
      ),
    );

    renderPanel(['SO403340']);

    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    fireEvent.click(await screen.findByRole('button', { name: /TPE-9204, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() => expect(screen.getByText('2 of 2 lines decided')).toBeInTheDocument());
    expect(
      await screen.findByText(
        'TPE-9204 line 2 reserves at a warehouse the board cannot address, so this confirmation leaves it out. Amend it to place the Reserve.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm 1 line' })).toBeInTheDocument();
  });

  it('names an approved Buy of a discontinued product that carries no reason, and does not count it', async () => {
    const board = twoLineOrder();
    getPlanningBoard.mockResolvedValue(
      withContribution(
        board,
        (entry) => entry.item_code === 'TPE-9204',
        (entry) => ({
          ...entry,
          item_flags: {
            dealer_hot_selling: false,
            dealer_hot_selling_where: [],
            project_hot_selling: false,
            project_hot_selling_where: [],
            dealer_classified: false,
            project_classified: false,
            discontinued: true,
            retail_classification_available: true,
          },
        }),
      ),
    );

    renderPanel(['SO403340']);

    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    fireEvent.click(await screen.findByRole('button', { name: /TPE-9204, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();

    await waitFor(() => expect(screen.getByText('2 of 2 lines decided')).toBeInTheDocument());
    expect(
      await screen.findByText(
        'TPE-9204 line 2 buys a discontinued product with no reason given, so this confirmation leaves it out. Amend it to give one.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm 1 line' })).toBeInTheDocument();
  });

  // The "no planning record, so no Confirm" state is deliberately GONE: pressing Confirm on
  // such an order now adopts it first. See "Confirm adopts first when it has to" below.
});

/**
 * Adopt on confirm (the captain: "why i cannot confirm the sales order partially? like i
 * decided few lines then i should be able to confirm partially right").
 *
 * They selected nine orders, decided lines across several of them, and every Confirm refused:
 * none had been adopted, so there was no planning record to confirm against. We let them do the
 * whole job and said no at the last step. Deciding lines and pressing Confirm IS the act, so the
 * press adopts first and then confirms, as one action.
 *
 * The refetch in the middle is not optional: `project_line_id` is null on every contribution
 * until the mirror lines exist, so a body built before adoption names nothing.
 */
describe('FulfilmentBoardPanel: Confirm adopts first when it has to', () => {
  /** A board for an order nobody has adopted: no planning record, no mirror lines. */
  function unadopted() {
    const board = boardOf([
      demand({ line_no: 1, item_code: 'WESERP10B' }),
      demand({ line_no: 2, item_code: 'TPE-9204' }),
    ]);
    return withContribution(
      { ...board, orders: board.orders.map((order) => ({ ...order, project_sales_order_id: null })) },
      () => true,
      (entry) => ({ ...entry, project_line_id: null }),
    );
  }

  function adopted() {
    return boardOf([
      demand({ line_no: 1, item_code: 'WESERP10B' }),
      demand({ line_no: 2, item_code: 'TPE-9204' }),
    ]);
  }

  async function approveOne() {
    fireEvent.click(await screen.findByRole('button', { name: /WESERP10B, 100 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    await waitFor(() => expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument());
  }

  it('offers Confirm on an order nobody has adopted, and never says planning has not started', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());

    renderPanel(['SO403340']);
    await approveOne();

    expect(screen.getByRole('button', { name: 'Confirm 1 line' })).toBeEnabled();
    // The old copy contradicted the counter beside it: "1 of 2 lines decided" and "nobody has
    // started planning" in the same breath, when the planner plainly had.
    expect(
      screen.queryByText('Nobody has started planning this sales order yet.'),
    ).not.toBeInTheDocument();
  });

  it('adopts, refetches, then posts the body built from the ids that arrived', async () => {
    getPlanningBoard.mockResolvedValueOnce(unadopted()).mockResolvedValue(adopted());
    adoptSalesOrder.mockResolvedValue({
      project_sales_order_id: 'pso-so-a',
      so_number: 'SO403340',
      review_state: 'needs_cs_review',
      already_adopted: false,
    });
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    renderPanel(['SO403340']);
    await approveOne();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    await waitFor(() => expect(adoptSalesOrder).toHaveBeenCalledWith('so-a'));
    await waitFor(() => expect(confirmSupply).toHaveBeenCalledTimes(1));
    const [psoId, body] = confirmSupply.mock.calls[0];
    expect(psoId).toBe('pso-so-a');
    // Built from the REFETCHED board: guessing an id before the mirror exists names nothing.
    expect(body.lines).toEqual([
      expect.objectContaining({ project_line_id: 'pl-so-a-1' }),
    ]);
  });

  it('does not adopt an order that already has a planning record', async () => {
    getPlanningBoard.mockResolvedValue(adopted());
    confirmSupply.mockResolvedValue({
      revision_no: 2,
      review_state: 'confirmed',
      inquiry_rows_created: 0,
      exceptions: [],
    });

    renderPanel(['SO403340']);
    await approveOne();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    await waitFor(() => expect(confirmSupply).toHaveBeenCalledTimes(1));
    expect(adoptSalesOrder).not.toHaveBeenCalled();
  });

  it('says so when adoption fails, and confirms nothing', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());
    adoptSalesOrder.mockRejectedValue(new Error('Another planning record already holds SO403340.'));

    renderPanel(['SO403340']);
    await approveOne();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm 1 line' }));

    expect(
      await screen.findByText(
        'Could not start planning this sales order: Another planning record already holds SO403340.',
      ),
    ).toBeInTheDocument();
    expect(confirmSupply).not.toHaveBeenCalled();
    // Nothing was committed, so the work is still the planner's.
    expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument();
  });

  it('shows no unmirrored notice on an order that was simply never adopted', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());

    renderPanel(['SO403340']);
    await approveOne();

    // That notice is for a mirror that is genuinely missing a line, which is a different
    // problem with a different fix. On a not-yet-adopted order it would name every line.
    expect(screen.queryByText(/not on the planning record yet/)).not.toBeInTheDocument();
  });
});

/**
 * Searching the board (the captain: "i need the search here also btw").
 *
 * The board is ONE already-fetched payload, so this filters the product ROWS in the browser: it
 * must not refetch, and it must not touch the selection. The headline totals do NOT move with
 * it - they describe the selection, not the rows on screen, which is the same lesson the day
 * window taught - so the filter states its own count instead, or a planner reads a filtered
 * board as the whole one.
 */
describe('FulfilmentBoardPanel: searching the product rows', () => {
  function catalogue() {
    return boardOf([
      demand({ line_no: 1, item_code: 'WESERP10B', product_name: 'Wall socket 10A white' }),
      demand({ line_no: 2, item_code: 'TPE-9204', product_name: 'Trunking 92mm' }),
      demand({ line_no: 3, item_code: 'CKS1050', product_name: 'Ceiling kit 50' }),
    ]);
  }

  function productRows() {
    return [...screen.getByTestId('fulfilment-board-matrix').querySelectorAll('tbody tr')].map(
      (row) => row.querySelector('th')?.textContent ?? '',
    );
  }

  async function searchFor(term: string) {
    const box = screen.getByPlaceholderText('Search sales order, customer, project or product');
    fireEvent.change(box, { target: { value: term } });
    await waitFor(() => expect(box).toHaveValue(term));
  }

  it('narrows the rows by item code, case-insensitively', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(productRows()).toEqual(['CKS1050', 'TPE-9204', 'WESERP10B']);

    await searchFor('tpe');

    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));
  });

  it('narrows the rows by product name too', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await searchFor('ceiling');

    await waitFor(() => expect(productRows()).toEqual(['CKS1050']));
  });

  it('never refetches: the board is one payload and this is a filter over its rows', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    const calls = getPlanningBoard.mock.calls.length;

    await searchFor('tpe');
    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));

    expect(getPlanningBoard.mock.calls.length).toBe(calls);
  });

  it('says how many rows are shown of how many, but only while a filter is on', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.queryByText(/products$/)).not.toBeInTheDocument();

    await searchFor('tpe');

    expect(await screen.findByText('1 of 3 products')).toBeInTheDocument();
  });

  it('leaves the selection-scoped sentence exactly where it was', async () => {
    const board = catalogue();
    getPlanningBoard.mockResolvedValue({ ...board, line_count: 161, past_line_count: 130 });

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await searchFor('tpe');

    // The product filter narrows the GRID and nothing else: the selection sentence describes
    // what is being planned, not what a search is showing.
    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));
    expect(screen.getByText('Planning 2 sales orders together')).toBeInTheDocument();
  });

  it('says nothing matches, rather than claiming the selection owes nothing', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await searchFor('zzzz');

    expect(await screen.findByText('No products match')).toBeInTheDocument();
    expect(screen.getByText('0 of 3 products')).toBeInTheDocument();
    // The "owes nothing" copy would be a flat lie: the selection owes plenty.
    expect(
      screen.queryByText('These sales orders owe nothing that can be planned'),
    ).not.toBeInTheDocument();
  });

  it('carries the term in the URL, so a filtered board is shareable', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await searchFor('tpe');

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        '/project-sales/fulfilment-planning?product=tpe',
        expect.objectContaining({ scroll: false }),
      ),
    );
  });

  it('opens on the term the URL carries', async () => {
    currentSearchParams = new URLSearchParams('product=ceiling');
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.getByPlaceholderText('Search sales order, customer, project or product')).toHaveValue('ceiling');
    await waitFor(() => expect(productRows()).toEqual(['CKS1050']));
  });

  it('clears with the X, and the whole board comes back', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await searchFor('tpe');
    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));

    fireEvent.click(screen.getByRole('button', { name: 'Clear the product search' }));

    await waitFor(() =>
      expect(productRows()).toEqual(['CKS1050', 'TPE-9204', 'WESERP10B']),
    );
    expect(screen.queryByText(/of 3 products/)).not.toBeInTheDocument();
  });
});

/**
 * The board is always fetched against the LIVE policy.
 *
 * The what-if existed to show what a fair weighting would do before one was switched on. The
 * fair policy is the live one now, so the offer was retired, and the banner that carried the way
 * back went with the banner itself (the captain: "this text is not needed at the top").
 */
describe('FulfilmentBoardPanel: the live policy, and only it', () => {
  function withPolicy(policy: Partial<BoardPolicy>) {
    const board = boardOf([demand()]);
    return { ...board, policy: { ...board.policy, ...policy } };
  }

  it('never asks the server for a previewed ranking', async () => {
    getPlanningBoard.mockResolvedValue(
      withPolicy({ name: 'Fair weighting', is_preview: false, discriminates_nothing: false }),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'week', false, {});
  });

  it('prints no policy identifiers anywhere above the grid', async () => {
    getPlanningBoard.mockResolvedValue(
      withPolicy({
        name: 'Fair weighting',
        factors: { need_by_date: 3, document_age: 1, customer_credit: 1, demand_class: 0 },
        discriminates_nothing: false,
      }),
    );

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/need_by_date/)).not.toBeInTheDocument();
    expect(screen.queryByText(/po_document_sequence/)).not.toBeInTheDocument();
    expect(
      screen.queryByText('Delivery date 3 · Order date 1 · Payment terms 1'),
    ).not.toBeInTheDocument();
  });
});

/**
 * The granularity travels with the selection (PLAN 13.3), so the whole board is one link.
 */
describe('FulfilmentBoardPanel: granularity in the URL', () => {
  it('opens on the granularity the URL names', async () => {
    currentSearchParams = new URLSearchParams('granularity=month');
    getPlanningBoard.mockResolvedValue(boardOf([demand()], {}, 'month'));

    renderPanel(['SO403340']);

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'month', false, {}),
    );
    expect(screen.getByLabelText('granularity')).toHaveValue('month');
  });

  it('falls back to week on a granularity nobody defined', async () => {
    currentSearchParams = new URLSearchParams('granularity=fortnightly');
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'week', false, {}),
    );
  });

  it('writes the granularity back when the planner turns the control', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), { target: { value: 'month' } });

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        '/project-sales/fulfilment-planning?granularity=month',
        expect.objectContaining({ scroll: false }),
      ),
    );
  });

  /**
   * A link can name an order that has since been delivered, closed, or was simply mistyped.
   * Opening a board of four when the link asked for five, and saying nothing, is the kind of
   * quiet subtraction that makes a shared link untrustworthy.
   */
  it('reports an order the board came back without, rather than swallowing it', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340', 'SO999999']);

    expect(
      await screen.findByText('SO999999 has nothing to plan on this board.'),
    ).toBeInTheDocument();
  });

  it('says nothing when every order asked for came back', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/has nothing to plan on this board/)).not.toBeInTheDocument();
  });
});

/**
 * The row axis, on screen (the captain: "how about if we want vertical is sales order, is
 * customer, is project").
 */
describe('FulfilmentBoardPanel: pivoting the rows', () => {
  function twoOrders() {
    return boardOf([
      demand({
        sales_order_id: 'so-a',
        so_number: 'SO000001',
        customer_name: 'ALPHA SDN BHD',
        project_label: 'TOWER A',
        line_no: 1,
        item_code: 'AAA',
        qty: '10',
      }),
      demand({
        sales_order_id: 'so-a',
        so_number: 'SO000001',
        customer_name: 'ALPHA SDN BHD',
        project_label: 'TOWER A',
        line_no: 2,
        item_code: 'BBB',
        qty: '20',
      }),
      demand({
        sales_order_id: 'so-b',
        so_number: 'SO000002',
        customer_name: 'ZULU SDN BHD',
        project_label: 'TOWER Z',
        line_no: 3,
        item_code: 'AAA',
        qty: '5',
      }),
    ]);
  }

  function rowHeaders() {
    return [...screen.getByTestId('fulfilment-board-matrix').querySelectorAll('tbody tr')].map(
      (row) => (row.querySelector('th')?.textContent ?? '').trim(),
    );
  }

  async function pivotTo(value: string) {
    fireEvent.change(screen.getByLabelText('rows'), { target: { value } });
    await waitFor(() => expect(screen.getByLabelText('rows')).toHaveValue(value));
  }

  it('offers the four axes, product first', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const select = screen.getByLabelText('rows');
    for (const label of ['Product', 'Sales order', 'Customer', 'Project']) {
      expect(within(select).getByRole('option', { name: label })).toBeInTheDocument();
    }
    expect(select).toHaveValue('product');
  });

  it('puts one row per sales order, holding every product that order owes', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(rowHeaders()).toEqual(['AAA', 'BBB']);

    await pivotTo('sales_order');

    await waitFor(() => expect(rowHeaders()).toEqual(['SO000001', 'SO000002']));
    // SO000001's two products in one cell: 10 + 20.
    expect(
      screen.getByRole('button', { name: /SO000001, 30 across 1 sales order/ }),
    ).toBeInTheDocument();
  });

  it('pivots to customer and to project', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await pivotTo('customer');
    await waitFor(() => expect(rowHeaders()).toEqual(['ALPHA SDN BHD', 'ZULU SDN BHD']));

    await pivotTo('project');
    await waitFor(() => expect(rowHeaders()).toEqual(['TOWER A', 'TOWER Z']));
  });

  it('opens the same breakdown from a pivoted cell, with the same lines', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await pivotTo('sales_order');

    fireEvent.click(
      await screen.findByRole('button', { name: /SO000001, 30 across 1 sales order/ }),
    );
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    // The dialog is unchanged: it lists LINES, which is what it always listed. Scoped to the
    // dialog because the board itself is a table too.
    const dialog = await screen.findByRole('dialog');
    const table = within(dialog).getByRole('table');
    expect(table.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(table.textContent).toContain('AAA');
    expect(table.textContent).toContain('BBB');
  });

  it('keeps a decision made under one axis visible under another', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel(['SO000001']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Decide a line while the rows are products. BBB is owed by one order only, so the cell
    // holds exactly the line this test is deciding.
    fireEvent.click(await screen.findByRole('button', { name: /BBB, 20 across 1 sales order/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }));
    closeDialog();
    await waitFor(() => expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument());

    // ...and it is the same line's decision when the rows become sales orders.
    await pivotTo('sales_order');
    await waitFor(() => expect(screen.getByText('1 of 2 lines decided')).toBeInTheDocument());
  });

  it('carries the axis in the URL, absent when it is the default', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await pivotTo('customer');

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith(
        '/project-sales/fulfilment-planning?rows=customer',
        expect.objectContaining({ scroll: false }),
      ),
    );
  });

  it('opens on the axis the URL names, and falls back to product on nonsense', async () => {
    currentSearchParams = new URLSearchParams('rows=project');
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.getByLabelText('rows')).toHaveValue('project');
    await waitFor(() => expect(rowHeaders()).toEqual(['TOWER A', 'TOWER Z']));
  });

  it('falls back to product on an axis nobody defined', async () => {
    currentSearchParams = new URLSearchParams('rows=warehouse');
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.getByLabelText('rows')).toHaveValue('product');
  });

  it('searches the four fields, and keeps whole cells while doing it', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    // A customer needle keeps only the product rows that customer owes...
    fireEvent.change(screen.getByPlaceholderText('Search sales order, customer, project or product'), {
      target: { value: 'zulu' },
    });

    await waitFor(() => expect(rowHeaders()).toEqual(['AAA']));
    // ...and AAA's cell still holds BOTH orders' lines: filtering inside a cell would print a
    // total that is not the cell's.
    expect(
      screen.getByRole('button', { name: /AAA, 15 across 2 sales orders/ }),
    ).toBeInTheDocument();
    expect(screen.getByText('1 of 2 products')).toBeInTheDocument();
  });

  it('counts the rows of whichever axis is showing', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await pivotTo('sales_order');

    fireEvent.change(screen.getByPlaceholderText('Search sales order, customer, project or product'), {
      target: { value: 'SO000002' },
    });

    await waitFor(() => expect(rowHeaders()).toEqual(['SO000002']));
    expect(screen.getByText('1 of 2 sales orders')).toBeInTheDocument();
  });
});

/**
 * Approve all / Confirm all approved (D3, PLAN-demo-followups-19aug-ladder-v2).
 *
 * Two orders, one undecided approvable line each: Approve all fills both blanks in the
 * draft (never a decision already taken), Confirm all approved asks before it writes
 * anything ("Confirm N decisions across M orders?"), and the write is ONE
 * `confirmMany` call grouped per order - never one call per order from the panel.
 */
describe('FulfilmentBoardPanel: Approve all / Confirm all approved', () => {
  function twoUndecidedOrders() {
    return boardOf([
      demand({
        sales_order_id: 'so-a',
        so_number: 'SO403340',
        line_no: 1,
        item_code: 'WESERP10B',
      }),
      demand({
        sales_order_id: 'so-b',
        so_number: 'SO398322',
        line_no: 1,
        item_code: 'WESERP20B',
      }),
    ]);
  }

  it('flips every undecided approvable line when Approve all is pressed', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.getByText('0 approved · 2 undecided')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approve all' }));

    expect(screen.getByText('2 approved · 0 undecided')).toBeInTheDocument();
  });

  it('opens the confirm dialog naming how many decisions across how many orders', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    fireEvent.click(screen.getByRole('button', { name: 'Approve all' }));

    fireEvent.click(screen.getByRole('button', { name: 'Confirm all approved' }));

    expect(
      await screen.findByText('Confirm 2 decisions across 2 orders?'),
    ).toBeInTheDocument();
  });

  it('posts ONE confirm-all call grouped per order, and renders each order its own result', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-a',
          ok: true,
          decision_revision: 1,
          inquiry_rows_created: 0,
          lines_decided: 1,
          lines_undecided: 0,
        },
        {
          pso_id: 'pso-so-b',
          ok: false,
          error: 'This line is not on this sales order any more.',
        },
      ],
    });

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    fireEvent.click(screen.getByRole('button', { name: 'Approve all' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm all approved' }));
    await screen.findByText('Confirm 2 decisions across 2 orders?');

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const body = confirmMany.mock.calls[0][0] as {
      orders: { pso_id: string; lines: { project_line_id: string }[] }[];
    };
    expect(body.orders).toHaveLength(2);
    const byPsoId = new Map(body.orders.map((order) => [order.pso_id, order]));
    expect(byPsoId.get('pso-so-a')?.lines.map((line) => line.project_line_id)).toEqual([
      'pl-so-a-1',
    ]);
    expect(byPsoId.get('pso-so-b')?.lines.map((line) => line.project_line_id)).toEqual([
      'pl-so-b-1',
    ]);

    expect(
      await screen.findByText('Confirm all: 1 of 2 orders confirmed'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('SO403340: confirmed as revision 1 (0 purchase rows handed over)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('SO398322: This line is not on this sales order any more.'),
    ).toBeInTheDocument();
  });

  it('leaves Approve all and Confirm all approved disabled with nothing to act on', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.getByRole('button', { name: 'Confirm all approved' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Approve all' }));

    expect(screen.getByRole('button', { name: 'Approve all' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Confirm all approved' })).not.toBeDisabled();
  });

  /**
   * BLOCKER (review): at day granularity `cells` only covers the visible 30-day window
   * (`DAY_WINDOW_COLUMNS`), so a line dated outside it used to be invisible to `allContributions`
   * (it flattened `cells`), and Approve all, the strip and Confirm all approved all silently
   * skipped it. The server's top-level `contributions` carries every line of the selection
   * regardless of the window; the panel must read that, not the cells.
   */
  it('approves and confirms a line the day window has scrolled away from, not only the ones on screen', async () => {
    const board = buildBoard(
      [
        demand({
          sales_order_id: 'so-a',
          so_number: 'SO403340',
          line_no: 1,
          item_code: 'WESERP10B',
          required_date: '2026-09-04',
        }),
        // Outside the 30-day window that opens on the earliest future date (2026-09-04): no
        // cell is emitted for this line, but it is still a real, decidable line of the
        // selection.
        demand({
          sales_order_id: 'so-b',
          so_number: 'SO398322',
          line_no: 1,
          item_code: 'WESERP20B',
          required_date: '2028-01-01',
        }),
      ],
      { today: TODAY, granularity: 'day' },
    );
    // The window really did leave one line off screen, so the assertions below mean something.
    expect(board.cells).toHaveLength(1);
    expect(board.contributions).toHaveLength(2);
    getPlanningBoard.mockResolvedValue(board);
    currentSearchParams = new URLSearchParams('granularity=day');

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    // The strip counts both lines, not only the one the window shows.
    expect(screen.getByText('0 approved · 2 undecided')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Approve all' }));
    expect(screen.getByText('2 approved · 0 undecided')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm all approved' }));
    expect(
      await screen.findByText('Confirm 2 decisions across 2 orders?'),
    ).toBeInTheDocument();
  });
});

/**
 * AC-C5 (retired 26 August 2026): NO legend row, and NO "already past" banner. The decision
 * strip's cards carry every label in its own colour, and the column headers already say
 * "Already past" over the periods they mean - so both were the screen restated in words.
 */
describe('FulfilmentBoardPanel: what was taken off the page', () => {
  it('shows no legend row on either view', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.queryByTestId('supply-legend')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    await waitFor(() =>
      expect(screen.queryByTestId('fulfilment-board-matrix')).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId('supply-legend')).not.toBeInTheDocument();
  });

  it('shows no "already past" banner, and the strip still carries the labels', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/lines are already past their delivery date/)).toBeNull();
    const strip = screen.getByTestId('decision-strip');
    expect(strip.textContent).toContain('Buy');
    expect(strip.textContent).toContain('Use BRW');
    expect(strip.textContent).toContain('Use own location');
  });
});

/**
 * AC-D2: the decision strip.
 *
 * The captain asked for "one page that shows, per line, what was SUGGESTED and what was
 * DECIDED, in the same words", and ruled that the page is this board, with cards.
 */
describe('FulfilmentBoardPanel: the decision strip', () => {
  /** The engine offered the pool; the planner bought the line whole. */
  const amendedBoard = () =>
    withContribution(
      boardOf([demand({ item_code: 'SRT382-6-DIY', qty: '71' })], {}),
      () => true,
      (entry) => ({
        ...entry,
        covered: true,
        proposed: {
          components: [
            {
              kind: 'reserve',
              rung: 'pool',
              qty: '71',
              location: 'BRW',
              warehouse_id: 'wh-BRW',
              reason: 'Free stock at BRW covers the need.',
            },
          ],
        },
        sources: [
          { kind: 'buy', rung: 'buy', qty: '71', location: null, reason: 'Bought, as confirmed.' },
        ],
        decision: {
          revision_no: 1,
          timely_spo_qty: '0',
          reserve: [],
          borrow: [],
          buy_qty: '71',
        },
      }),
    );

  it('states both figures per kind and marks the pair that moved', async () => {
    getPlanningBoard.mockResolvedValue(amendedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    const shared = screen.getByTestId('decision-strip-shared');
    expect(within(shared).getByText('71')).toBeInTheDocument();
    expect(screen.getByTestId('decision-strip-changed-shared')).toBeInTheDocument();

    const buy = screen.getByTestId('decision-strip-buy');
    expect(within(buy).getByText('71')).toBeInTheDocument();
    expect(screen.getByTestId('decision-strip-changed-buy')).toBeInTheDocument();
  });

  it('sits above whichever view is on screen', async () => {
    getPlanningBoard.mockResolvedValue(amendedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    const strip = screen.getByTestId('decision-strip');
    const matrix = screen.getByTestId('fulfilment-board-matrix');
    expect(strip.compareDocumentPosition(matrix)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it('filters the grid to the cells carrying that kind, and clears on a second press', async () => {
    // Two products: one bought, one covered from the pool. Pressing Shared has to leave the
    // pooled one and take the bought one away.
    const board = withContribution(
      boardOf(
        [
          demand({ line_no: 1, item_code: 'SRT382-6-DIY', qty: '71' }),
          demand({ line_no: 2, item_code: 'WESERP10B', qty: '10' }),
        ],
        { 'WESERP10B|BRW-BB': '999' },
      ),
      () => true,
      (entry) => entry,
    );
    getPlanningBoard.mockResolvedValue(board);

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.getByText('SRT382-6-DIY')).toBeInTheDocument();
    expect(screen.getByText('WESERP10B')).toBeInTheDocument();

    // WESERP10B has free stock at its own location, so the ladder takes it on the group rung
    // and SRT382-6-DIY is bought. Own keeps the first and drops the second.
    fireEvent.click(screen.getByTestId('decision-strip-own'));
    await waitFor(() => {
      expect(screen.queryByText('SRT382-6-DIY')).not.toBeInTheDocument();
    });
    expect(screen.getByText('WESERP10B')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('decision-strip-own'));
    await waitFor(() => {
      expect(screen.getByText('SRT382-6-DIY')).toBeInTheDocument();
    });
  });
});

/**
 * The card, the figures above it and BOTH views are one reading or they are none.
 *
 * Two ways they came apart, both found in review: the list view ignored the pressed card
 * entirely (it kept receiving every contribution while the card sat aria-pressed), and the
 * strip was summed over the whole selection while the grid was filtered over its cells - which
 * at day granularity is a 30-day window, so a card could read a figure off lines the board
 * could not show and then empty itself when pressed.
 */
describe('FulfilmentBoardPanel: the strip and the views agree', () => {
  /** One bought line, one covered from its own location. */
  const mixedBoard = () =>
    boardOf(
      [
        demand({ line_no: 1, item_code: 'SRT382-6-DIY', qty: '71' }),
        demand({ line_no: 2, item_code: 'WESERP10B', qty: '10' }),
      ],
      { 'WESERP10B|BRW-BB': '999' },
    );

  it('filters the LIST view by the pressed card, not only the grid', async () => {
    getPlanningBoard.mockResolvedValue(mixedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    await screen.findByText('SRT382-6-DIY');
    expect(screen.getByText('WESERP10B')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('decision-strip-own'));
    await waitFor(() => {
      expect(screen.queryByText('SRT382-6-DIY')).not.toBeInTheDocument();
    });
    expect(screen.getByText('WESERP10B')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('decision-strip-own'));
    await waitFor(() => {
      expect(screen.getByText('SRT382-6-DIY')).toBeInTheDocument();
    });
  });

  it('never shows a figure the view cannot produce: pressing a card leaves something on screen', async () => {
    getPlanningBoard.mockResolvedValue(mixedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Every card carrying a figure must leave at least one product row when pressed. A card
    // that empties the board is the exact defect this rule exists to prevent.
    for (const kind of ['buy', 'own']) {
      fireEvent.click(screen.getByTestId(`decision-strip-${kind}`));
      await waitFor(() => {
        expect(screen.getByTestId('fulfilment-board-matrix')).toBeInTheDocument();
      });
      expect(screen.queryByText('No products match')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId(`decision-strip-${kind}`));
    }
  });

  it('disables a card nothing on the board is that kind of supply', async () => {
    getPlanningBoard.mockResolvedValue(mixedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Nothing here is borrowed, so that card reads 0 / 0 and cannot be pressed - it keeps
    // its place, because it stands for one of the ladder's four questions and a card that
    // came and went would move every card beside it.
    expect(screen.getByTestId('decision-strip-borrow_order')).toBeDisabled();
    expect(screen.getByTestId('decision-strip-buy')).not.toBeDisabled();
    // `incoming` is the exception (ruled 27 August 2026): it is not a question, it is what
    // a decision frozen under an older ladder carries, so at 0 / 0 it is not shown at all.
    expect(screen.queryByTestId('decision-strip-incoming')).not.toBeInTheDocument();
  });
});
