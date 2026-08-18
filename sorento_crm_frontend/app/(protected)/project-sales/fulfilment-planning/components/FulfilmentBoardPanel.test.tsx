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

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getPlanningBoard = vi.fn();
const confirmSupply = vi.fn();
const adoptSalesOrder = vi.fn();

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: (...args: unknown[]) => adoptSalesOrder(...args),
  getSupply: vi.fn(),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
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
  }: {
    value: string;
    onChange: (next: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select aria-label="granularity" value={value} onChange={(e) => onChange(e.target.value)}>
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
  BoardGranularity,
  BoardPolicy,
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
});

/**
 * Title left, actions right (captain, with a screenshot of Back overlapping the title).
 *
 * `flex items-center justify-between` does not wrap, so a long title and a control row
 * collide at narrow widths and push the whole page sideways - the exact failure the
 * responsive-header rule in CLAUDE.md exists to prevent.
 */
describe('FulfilmentBoardPanel: the header', () => {
  it('puts Back to the worklist in the actions on the right, after the granularity control', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const actions = screen.getByTestId('board-header-actions');
    const back = within(actions).getByRole('button', { name: 'Back to the worklist' });
    const granularity = within(actions).getByLabelText('granularity');
    expect(back.compareDocumentPosition(granularity)).toBe(Node.DOCUMENT_POSITION_PRECEDING);
  });

  it('still returns to the worklist', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));
    const onBack = vi.fn();

    renderPanel(['SO403340'], onBack);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'Back to the worklist' }));
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
    expect(
      screen.getByText('1 of 2 lines are already past their required date'),
    ).toBeInTheDocument();
  });

  /**
   * The banner counts the SELECTION, not the columns on screen. The server sends
   * `past_line_count` / `line_count` at the top level for exactly this reason: summing
   * `cell.past_count` counts only what a window happens to be showing, so the same board read
   * differently on day than on week. The per-cell count stays correct for the cell itself.
   */
  it('reads the selection-scoped totals rather than summing the cells on screen', async () => {
    const board = boardOf([
      demand({ line_no: 1, required_date: '2022-07-03' }),
      demand({ line_no: 2, required_date: '2026-09-04' }),
    ]);
    getPlanningBoard.mockResolvedValue({
      ...board,
      // What the server counted over the whole selection; the two cells on screen are a
      // fraction of it, and summing them would report "1 of 2".
      line_count: 161,
      past_line_count: 130,
    });

    renderPanel();

    expect(
      await screen.findByText('130 of 161 lines are already past their required date'),
    ).toBeInTheDocument();
  });

  it('states plainly how much of the selection is already past, and explains nothing', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ line_no: 1, required_date: '2022-07-03' }),
        demand({ line_no: 2, required_date: '2026-09-04' }),
      ]),
    );

    renderPanel();

    expect(
      await screen.findByText('1 of 2 lines are already past their required date'),
    ).toBeInTheDocument();
    // The old copy described a column that no longer exists, and a tint that needs a
    // paragraph is a tint that failed. No feature explanations in the UI (CLAUDE.md).
    expect(screen.queryByText(/Overdue column/)).not.toBeInTheDocument();
    expect(screen.queryByText(/rather than spread/)).not.toBeInTheDocument();
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

describe('FulfilmentBoardPanel: the ranking policy (13.5)', () => {
  /** A board with the policy the server actually sends, flag and all. */
  function boardWithPolicy(policy: Partial<BoardPolicy>) {
    const board = boardOf([demand()]);
    return { ...board, policy: { ...board.policy, ...policy } };
  }

  it('names the policy the board ranked by', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();

    expect(await screen.findByText("Today's rule (PO document sequence)")).toBeInTheDocument();
  });

  /**
   * Deviation 1: `discriminates_nothing` is the SERVER's verdict, not something the screen
   * infers from the weights. The server also catches "weighted but constant" - every row on
   * this board is project-class, so `demand_class` can carry a real weight and still separate
   * nobody - which no reading of the factor map on this side can see.
   */
  it('says the ranking is flat when the SERVER says the policy discriminates nothing', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({
        name: 'Weighted but useless here',
        // Deliberately non-zero weights: a screen deriving the answer from these would call
        // this policy healthy and say nothing.
        factors: { demand_class: 3, need_by_date: 0 },
        discriminates_nothing: true,
      }),
    );

    renderPanel();

    expect(
      await screen.findByText(
        'This policy weights nothing that separates these rows, so every one scores the same and the ranking is flat.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the weights, and no warning, when the server says the policy does discriminate', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({
        name: 'Fulfilment board preview',
        factors: { need_by_date: 3, document_age: 1 },
        discriminates_nothing: false,
      }),
    );

    renderPanel();

    expect(await screen.findByText('need_by_date 3 · document_age 1')).toBeInTheDocument();
    expect(
      screen.queryByText(/the ranking is flat/),
    ).not.toBeInTheDocument();
  });

  it('labels a previewed ranking as not live', async () => {
    getPlanningBoard.mockResolvedValue(
      boardWithPolicy({ name: 'Fulfilment board preview', is_preview: true }),
    );

    renderPanel();

    expect(await screen.findByText('Preview, not live')).toBeInTheDocument();
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

  it('previews a fairer weighting without activating it', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'Preview a fairer weighting' }));

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'week', true, {}),
    );
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
      await screen.findByText('These sales orders owe nothing that can be planned'),
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

    expect(await screen.findByText('Nothing is owed in these dates')).toBeInTheDocument();
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

  it('states what confirming does NOT do, and links to no list this order is absent from', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      screen.getByText(
        'Confirmed Buy rows reach purchasing on the sales order itself. An adopted order raises no purchasing task and sends no notification.',
      ),
    ).toBeInTheDocument();
    // The Order Inquiry list is project-scoped, so an adopted order is not on it: a link would
    // open a list without the thing it promised.
    expect(screen.queryByRole('link', { name: /order inquir/i })).not.toBeInTheDocument();
  });

  /**
   * Adoption mirrored the order's open lines when it ran, so a later upload can add a core line
   * with no mirror. The order is still confirmable; that line is not, and the planner may well
   * have approved it - so it is NAMED rather than silently dropped.
   */
  it('names a decided line that has no mirror, and does not count it in the Confirm', async () => {
    const board = twoLineOrder();
    getPlanningBoard.mockResolvedValue({
      ...board,
      cells: board.cells.map((cell) => ({
        ...cell,
        contributions: cell.contributions.map((entry) =>
          entry.item_code === 'TPE-9204' ? { ...entry, project_line_id: null } : entry,
        ),
      })),
    });
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
    return {
      ...board,
      orders: board.orders.map((order) => ({ ...order, project_sales_order_id: null })),
      cells: board.cells.map((cell) => ({
        ...cell,
        contributions: cell.contributions.map((entry) => ({ ...entry, project_line_id: null })),
      })),
    };
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
