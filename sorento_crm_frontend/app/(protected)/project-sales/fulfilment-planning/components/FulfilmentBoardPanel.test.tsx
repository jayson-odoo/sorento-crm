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
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const routerReplace = vi.fn();
let currentSearchParams = new URLSearchParams('');

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: (...args: unknown[]) => routerReplace(...args),
  }),
  usePathname: () => '/project-sales/fulfilment-planning',
  useSearchParams: () => currentSearchParams,
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({
    resetToDefaults: vi.fn(),
    isLoading: false,
  }),
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
  // S4 (`useLineDraftMutation`): no test here presses Save deep enough to reach these -
  // that interaction is `BoardLineDecisionPanel.test.tsx`'s, against a plain `vi.fn()`
  // `onDecide` - but `decide()` closes over them regardless, so an undefined export would
  // throw the moment it did.
  putLineDraft: vi.fn().mockResolvedValue({
    decision: { verdict: 'approved' },
    saved_by: 'Test Planner',
    saved_at: '2026-09-03T00:00:00Z',
  }),
  deleteLineDraft: vi.fn().mockResolvedValue(undefined),
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
      failingLines: {
        line_no?: number | null;
        item_code?: string | null;
        reason: string;
      }[] = [],
    ) {
      super(message);
      this.name = 'ConfirmSupplyError';
      this.failingLines = failingLines;
    }
  },
}));

const getPlanningChangeBatch = vi.fn();
vi.mock('../../_shared/services/planningChangeService', () => ({
  listPlanningChangeBatches: vi.fn(),
  getPlanningChangeBatch: (...args: unknown[]) =>
    getPlanningChangeBatch(...args),
  updatePlanningChangeRow: vi.fn(),
  applyPlanningChanges: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

// S4: `decide()` names the saver off the session (R-F). A harmless authenticated session -
// the popover-content assertion is left to `BoardDecisionPill.test.tsx`.
vi.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { id: 'user-1', name: 'Test Planner' } },
    status: 'authenticated',
  }),
}));

/**
 * `BoardTransfersPanel` (D4) is on this screen now, above the matrix. Its own behaviour is
 * `BoardTransfersPanel.test.tsx`'s; what this file owes is a harmless mock so the board can
 * render without a real query or a real permission check.
 */
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => false,
}));
vi.mock('../../_shared/hooks/useBoardTransfers', () => ({
  // The real key, because the confirm hook invalidates it by name (D6).
  BOARD_TRANSFERS_KEY: 'board-stock-transfers',
  useBoardTransfers: () => ({
    data: { data: [] },
    isLoading: false,
    error: undefined,
  }),
  useBoardTransferMutations: () => ({
    approve: { mutate: vi.fn(), isPending: false },
    approveAll: { mutate: vi.fn(), isPending: false },
  }),
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

import { toast } from 'sonner';
import {
  FulfilmentBoardPanel,
  unpostableNotices,
} from './FulfilmentBoardPanel';
import {
  buildBoard,
  type BoardDemandLine,
} from '../../_shared/lib/__testsupport__/boardFixture';
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
  const apply = (entry: BoardContribution) =>
    match(entry) ? transform(entry) : entry;
  return {
    ...board,
    cells: board.cells.map((cell) => ({
      ...cell,
      contributions: cell.contributions.map(apply),
    })),
    contributions: board.contributions.map(apply),
  };
}

function renderPanel(
  soNumbers = ['SO403340', 'SO398322'],
  onBack: () => void = vi.fn(),
  batchId: string | null = null,
) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel
        soNumbers={soNumbers}
        onBack={onBack}
        batchId={batchId}
      />
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

/**
 * The cell dialog opens on its STOCK tab, so a test that reads or decides a LINE presses
 * the other tab first - the same press a planner makes.
 *
 * Not cosmetic: Radix unmounts the inactive panel, so without this there is no lines grid
 * in the tree at all. The dialog is opened from a cell and never from a line, which is why
 * Stock is what it defaults to.
 *
 * Radix's TabsTrigger switches on MOUSE DOWN; a bare `click` leaves the old panel up.
 */
function openLinesTab() {
  const tab = screen.getByRole('tab', { name: /^Contributing lines/ });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
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
  /**
   * R12/D2: "Back to sales orders" moved off the header row and under the gear on the action
   * bar, beside Undo all - the header row is now only the controls that decide what the board
   * SHOWS, and the way off the screen no longer competes with them for the same glance.
   */
  it('has no Back to sales orders button in the header actions any more', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const actions = screen.getByTestId('board-header-actions');
    expect(
      within(actions).queryByRole('button', { name: 'Back to sales orders' }),
    ).not.toBeInTheDocument();
  });

  it('calls back from the gear on the action bar, which is now the sales-order list', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));
    const onBack = vi.fn();

    renderPanel(['SO403340'], onBack);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.keyDown(screen.getByRole('button', { name: 'Board actions' }), {
      key: 'Enter',
    });
    fireEvent.click(
      screen.getByRole('menuitem', { name: 'Back to sales orders' }),
    );

    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('lets the header wrap instead of overlapping the title', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const header = screen.getByTestId('board-header');
    expect(header.className).toContain('flex-col');
    expect(header.className).toContain('sm:flex-row');
    expect(screen.getByTestId('board-header-title').className).toContain(
      'min-w-0',
    );
    expect(screen.getByTestId('board-header-actions').className).toContain(
      'flex-wrap',
    );
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
    getPlanningBoard.mockResolvedValue(
      boardOf([demand({ required_date: '2026-11-04' })]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const header = matrix.querySelector('[data-bucket="2026-11-02"]');
    expect(header?.textContent).toBe('2 Nov 2026');
  });

  it('strips the abbreviation from the cell dialog’s title too', async () => {
    const board = boardOf([
      demand({ required_date: '2026-11-04', item_code: 'WESERP10B' }),
    ]);
    getPlanningBoard.mockResolvedValue({
      ...board,
      dateBuckets: board.dateBuckets.map((bucket) => ({
        ...bucket,
        label: `w/c ${bucket.label}`,
      })),
    });

    renderPanel(['SO403340']);
    fireEvent.click(
      await screen.findByRole('button', {
        name: /WESERP10B, 100 across 1 sales order/,
      }),
    );

    expect(
      await screen.findByText('WESERP10B · 2 Nov 2026'),
    ).toBeInTheDocument();
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
    expect(
      matrix.querySelector('[data-bucket="2026-11-02"]')?.textContent,
    ).toBe('2 Nov 2026');
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
    expect(
      matrix
        .querySelector('[data-bucket="2026-08-31"]')
        ?.getAttribute('data-past'),
    ).toBe('false');
    // Its quantity stands alone in its own cell rather than being rolled into a later one.
    expect(
      within(matrix).getByRole('button', {
        name: /WESERP10B, 40 across 1 sales order/,
      }),
    ).toBeInTheDocument();
    expect(
      within(matrix).getByRole('button', {
        name: /WESERP10B, 100 across 1 sales order/,
      }),
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
    expect(
      matrix
        .querySelector('[data-bucket="2026-08-17"]')
        ?.getAttribute('data-past'),
    ).toBe('false');
    // AC-C5 (26 August 2026): the banner that used to say so is gone. What remains is the
    // per-bucket tint, which is what the header already announces.
    expect(
      screen.queryByText(/lines are already past their delivery date/),
    ).toBeNull();
  });

  it('renders the products down the side', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ item_code: 'WESERP10B' }),
        demand({ item_code: 'TPE-9204', line_no: 2 }),
      ]),
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
        demand({
          sales_order_id: 'so-a',
          so_number: 'SO403340',
          line_no: 1,
          qty: '100',
        }),
        demand({
          sales_order_id: 'so-b',
          so_number: 'SO398322',
          line_no: 2,
          qty: '74',
        }),
      ]),
    );

    renderPanel();

    const cell = await screen.findByRole('button', {
      name: /WESERP10B, 174 across 2 sales orders/,
    });
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

    // S3b: the strip is pills now, not a `·`-joined title string - one pill per location,
    // folding what does not fit into "+N". jsdom lays every element out at width 0, so only
    // the first pill shows and the second folds behind "+1" (the same trap
    // `PillOverflow.test.tsx` documents); both locations are still present either way.
    const cell = await screen.findByRole('button', {
      name: /WESERP10B, 43 across 1 sales order/,
    });
    // Scoped to the visible pill row (`role="group"`), not just the cell: the hidden
    // measuring row repeats the same label text off-screen so it can size itself, and a
    // plain `getByText` finds that copy too.
    const pills = within(cell).getByRole('group', { name: 'Locations' });
    expect(within(pills).getByText('BRW-BB 22')).toBeInTheDocument();
    expect(within(pills).getByText('+1')).toBeInTheDocument();
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
          demand({
            sales_order_id: 'so-a',
            so_number: 'SO403340',
            line_no: 1,
            qty: '100',
            required_date: '2026-09-04',
          }),
          demand({
            sales_order_id: 'so-b',
            so_number: 'SO398322',
            line_no: 2,
            qty: '100',
            required_date: '2026-09-02',
          }),
        ],
        { 'WESERP10B|BRW-BB': '100' },
      ),
    );

    renderPanel();

    // The matrix cell never printed a sales-order number - this waited for text that could
    // never appear, and timed out instead of asserting anything. `fulfilment-board-matrix`
    // is what the other tests in this file already wait on.
    await screen.findByTestId('fulfilment-board-matrix');
    // The count is gone from the cell (the captain, 27 Aug); the flag stays in the data.
    expect(screen.queryByText('1 contested')).toBeNull();
  });

  it('leaves a product-and-date nobody owes blank, because a blank cell is not a zero', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({
          item_code: 'WESERP10B',
          line_no: 1,
          required_date: '2026-09-04',
        }),
        demand({
          item_code: 'TPE-9204',
          line_no: 2,
          required_date: '2026-12-01',
        }),
      ]),
    );

    renderPanel();

    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    const empty = matrix.querySelector('[data-cell="TPE-9204|2026-08-31"]');
    expect(empty).not.toBeNull();
    expect(empty?.textContent).toBe('');
    // Scoped to /across/ - a cell button's own accessible name - because the source strip's
    // pills (S3b) are `role="button"` too, and an unscoped query would also count those.
    expect(
      within(matrix).getAllByRole('button', { name: /across/ }).length,
    ).toBe(2);
  });
});

/**
 * NO COMMIT SECTION (R13, UAC D5). The per-order commit cards, their own "N of M lines
 * decided" counter and "Confirms N, leaves M undecided" copy are gone with it: the one counter
 * left is the board-wide bar (`board-confirm-summary`, UAC D1/D3), and a plannable line nobody
 * touches is confirmed as the engine's own suggestion (R11) rather than needing an explicit
 * Approve to count.
 */
describe('FulfilmentBoardPanel: no commit section (D5)', () => {
  it('carries no per-order commit card, decided counter or "this order" Confirm button', async () => {
    getPlanningBoard.mockResolvedValue(
      boardOf([
        demand({ sales_order_id: 'so-a', so_number: 'SO403340', line_no: 1 }),
        demand({ sales_order_id: 'so-b', so_number: 'SO398322', line_no: 2 }),
      ]),
    );

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(screen.queryByText(/lines decided/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Confirms .* leaves/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Confirm this order' }),
    ).not.toBeInTheDocument();
  });
});

/**
 * The counter the captain asked to see (D1/D3), at the granularity that used to lie about it.
 *
 * The board-wide bar is built off `board.data.contributions` - the SELECTION, never `cells`,
 * which at day granularity is a 30-day window. So a forty-line order reads "40 to confirm" at
 * both granularities, never "3 to confirm" because only three cells made it onto the day view.
 */
describe('FulfilmentBoardPanel: the confirm counter is selection-scoped, not window-scoped', () => {
  /** Three lines inside the first day window, thirty-seven far outside it. */
  function fortyLines() {
    const inside = Array.from({ length: 3 }, (_unused, index) =>
      demand({
        line_no: index + 1,
        item_code: `IN-${index}`,
        required_date: '2026-09-04',
      }),
    );
    // A Monday: `weekStart` of a Monday is itself, so the day and week bucket keys for this
    // date coincide and a contribution's `key` (which embeds the bucket key) survives the
    // granularity switch below - a Tuesday would not (bucketKeyFor: 3 Jan / 4 Jan bucket
    // themselves differently for day vs week), and the verdict would silently un-decide.
    const outside = Array.from({ length: 37 }, (_unused, index) =>
      demand({
        line_no: 100 + index,
        item_code: `OUT-${index}`,
        required_date: '2028-01-03',
      }),
    );
    return [...inside, ...outside];
  }

  /** Expands the one row of the just-opened cell dialog - every line here is on SO403340. */
  function expandRow() {
    openLinesTab();
    fireEvent.click(screen.getByText('SO403340'));
  }

  it('counts all forty lines to confirm at day granularity, where only three are on screen', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation(
      (_orders: unknown, granularity: BoardGranularity) =>
        Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    // R11: every plannable line is a suggestion nobody has rejected, so all forty count.
    expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
      '40 to confirm · 0 rejected',
    );

    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'day' },
    });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        {},
      ),
    );

    // The window shows three of the forty; the counter must still say forty. Scoped to
    // /across/ - a cell button's own accessible name - because the source strip's pills
    // (S3b) are `role="button"` too, and an unscoped query would also count those.
    const matrix = await screen.findByTestId('fulfilment-board-matrix');
    expect(
      within(matrix).getAllByRole('button', { name: /across/ }),
    ).toHaveLength(3);
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
        '40 to confirm · 0 rejected',
      ),
    );
  });

  it('counts a rejection against the whole selection, not the window', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation(
      (_orders: unknown, granularity: BoardGranularity) =>
        Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'day' },
    });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        {},
      ),
    );

    fireEvent.click(
      await screen.findByRole('button', {
        name: /IN-0, 100 across 1 sales order/,
      }),
    );
    expandRow();
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'This line is being replaced.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    closeDialog();

    await waitFor(() =>
      expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
        '39 to confirm · 1 rejected',
      ),
    );
  });

  it('keeps a rejected verdict counted after the window scrolls past the cell it was made on', async () => {
    const lines = fortyLines();
    getPlanningBoard.mockImplementation(
      (_orders: unknown, granularity: BoardGranularity) =>
        Promise.resolve(boardOf(lines, {}, granularity)),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Decide a line that only the WEEK board shows...
    fireEvent.click(
      await screen.findByRole('button', {
        name: /OUT-0, 100 across 1 sales order/,
      }),
    );
    expandRow();
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'This line is being replaced.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    closeDialog();
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
        '39 to confirm · 1 rejected',
      ),
    );

    // ...then move to a window that does not contain it. The verdict is still the planner's.
    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'day' },
    });
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        {},
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
        '39 to confirm · 1 rejected',
      ),
    );
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

    expect(
      screen.queryByText("Today's rule (PO document sequence)"),
    ).not.toBeInTheDocument();
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

    expect(
      screen.queryByText('Delivery date 3 · Order date 1'),
    ).not.toBeInTheDocument();
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
    expect(
      within(select).getByRole('option', { name: 'By day' }),
    ).toBeInTheDocument();
    expect(
      within(select).getByRole('option', { name: 'By week' }),
    ).toBeInTheDocument();
    expect(
      within(select).getByRole('option', { name: 'By month' }),
    ).toBeInTheDocument();
  });

  it('asks the service for the granularity the planner chose', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'month' },
    });

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'month',
        false,
        {},
      ),
    );
  });

  /** Deviation 7: the day view scrolls a 30-day window, and the server is told which one. */
  it('offers a window to scroll only at day granularity, and sends it', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      screen.queryByRole('button', { name: 'Later days' }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'day' },
    });
    // Wait for the day board to land before scrolling: the window is anchored on the board's
    // own first dated bucket, so scrolling a board that has not arrived anchors on nothing.
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        {},
      ),
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'day',
        false,
        expect.objectContaining({
          dayWindow: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        }),
      ),
    );
  });

  /**
   * The step is the contract's thirty days, and the anchor is the window the planner asked
   * for. Stepping by the dated columns that came back skipped or re-showed days whenever the
   * server sent fewer than thirty, and a window with no dated column at all could not move.
   */
  it('steps by thirty days even when the server sent fewer dated columns', async () => {
    const dayBoard = boardOf(
      [demand({ required_date: '2026-09-04' })],
      {},
      'day',
    );
    getPlanningBoard.mockResolvedValue({
      ...dayBoard,
      dateBuckets: dayBoard.dateBuckets
        .filter((bucket) => bucket.kind === 'dated')
        .slice(0, 5),
    });
    currentSearchParams = new URLSearchParams('granularity=day');

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    const first = dayBoard.dateBuckets.find(
      (bucket) => bucket.kind === 'dated',
    )?.start;
    expect(first).toBe('2026-09-04');

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(
        ['SO403340'],
        'day',
        false,
        {
          dayWindow: '2026-10-04',
        },
      ),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(
        ['SO403340'],
        'day',
        false,
        {
          dayWindow: '2026-11-03',
        },
      ),
    );
  });

  it('still moves off a window with no dated column in it', async () => {
    const dayBoard = boardOf(
      [demand({ required_date: '2026-09-04' })],
      {},
      'day',
    );
    getPlanningBoard.mockResolvedValue(dayBoard);
    currentSearchParams = new URLSearchParams('granularity=day');

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(
        ['SO403340'],
        'day',
        false,
        {
          dayWindow: '2026-10-04',
        },
      ),
    );

    // The next window has nothing owed in it: no cells, no dated columns.
    getPlanningBoard.mockResolvedValue({
      ...dayBoard,
      dateBuckets: [],
      cells: [],
    });
    fireEvent.click(await screen.findByRole('button', { name: 'Later days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(
        ['SO403340'],
        'day',
        false,
        {
          dayWindow: '2026-11-03',
        },
      ),
    );
    await screen.findByText('Nothing is outstanding in these dates');

    fireEvent.click(screen.getByRole('button', { name: 'Earlier days' }));
    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenLastCalledWith(
        ['SO403340'],
        'day',
        false,
        {
          dayWindow: '2026-10-04',
        },
      ),
    );
  });

  it('asks the server for the live policy, the preview offer having been retired', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // The what-if existed to show a fair weighting before one was switched on. It is now the
    // live one, so every board is fetched against the live policy and nothing offers to
    // preview it against itself.
    expect(getPlanningBoard).toHaveBeenCalledWith(
      ['SO403340'],
      'week',
      false,
      {},
    );
    expect(
      screen.queryByRole('button', { name: 'Preview a fairer weighting' }),
    ).not.toBeInTheDocument();
  });
});

describe('FulfilmentBoardPanel: states', () => {
  it('reports a failure instead of an empty grid', async () => {
    getPlanningBoard.mockRejectedValue(new Error('Backend is down'));

    renderPanel();

    expect(
      await screen.findByText('The planning board could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Backend is down')).toBeInTheDocument();
  });

  it('says so when the selection owes nothing plannable', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([]));

    renderPanel();

    expect(
      await screen.findByText(
        'Nothing is outstanding on these sales orders that can be planned',
      ),
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

    expect(
      await screen.findByText('Nothing is outstanding in these dates'),
    ).toBeInTheDocument();
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
    expect(
      screen.queryByText('The planning board could not be loaded'),
    ).not.toBeInTheDocument();
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
/**
 * ONE CONFIRM (R11, UAC D1/D2/D4/D6). The board no longer builds its body from ticked rows;
 * `confirmLinesFor` posts every plannable, non-rejected line as its own suggestion once the
 * planner presses the single header button, and every order writes in ONE `confirmMany` call.
 */
describe('FulfilmentBoardPanel: Confirm actually confirms', () => {
  function twoLineOrder() {
    return boardOf([
      demand({ line_no: 1, item_code: 'WESERP10B' }),
      demand({ line_no: 2, item_code: 'TPE-9204' }),
    ]);
  }

  async function openConfirmDialog() {
    fireEvent.click(await screen.findByTestId('board-confirm'));
    await screen.findByRole('alertdialog');
  }

  it('posts every plannable line as the engine’s own suggestion, in one confirmMany call (D2)', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-a',
          ok: true,
          decision_revision: 1,
          inquiry_rows_created: 0,
          transfers_written: 0,
        },
      ],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    expect(body.orders).toHaveLength(1);
    expect(body.orders[0].pso_id).toBe('pso-so-a');
    expect(
      body.orders[0].lines
        .map((line: { project_line_id: string }) => line.project_line_id)
        .sort(),
    ).toEqual(['pl-so-a-1', 'pl-so-a-2']);
  });

  it('names the D6 toast numbers: lines confirmed, transfers proposed, inquiry rows', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-a',
          ok: true,
          decision_revision: 1,
          inquiry_rows_created: 1,
          transfers_written: 1,
        },
      ],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        '2 lines confirmed · 1 transfer proposed · 1 inquiry row',
      ),
    );
  });

  it('names the movements it KEPT beside the ones it raised (R16)', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-a',
          ok: true,
          decision_revision: 2,
          inquiry_rows_created: 0,
          transfers_written: 1,
          transfers_kept: 3,
        },
      ],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        '2 lines confirmed · 1 transfer proposed · 3 kept · 0 inquiry rows',
      ),
    );
  });

  it('refetches the board once the confirmation lands', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-a', ok: true, decision_revision: 1 }],
    });

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    const boardCallsBefore = getPlanningBoard.mock.calls.length;

    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(getPlanningBoard.mock.calls.length).toBeGreaterThan(
        boardCallsBefore,
      ),
    );
  });

  it('keeps the draft and shows the order’s own refusal when the server refuses it', async () => {
    getPlanningBoard.mockResolvedValue(twoLineOrder());
    confirmMany.mockResolvedValue({
      results: [
        {
          pso_id: 'pso-so-a',
          ok: false,
          error: 'The sales order moved on underneath this plan.',
        },
      ],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(
      await screen.findByText(
        'SO403340: The sales order moved on underneath this plan.',
      ),
    ).toBeInTheDocument();
    // The planner does not lose their work to a refusal: still 2 plannable to confirm.
    expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
      '2 to confirm · 0 rejected',
    );
  });

  /**
   * Adoption mirrored the order's open lines when it ran, so a later upload can add a core line
   * with no mirror. The order is still confirmable; that line is not, and it is NAMED rather
   * than silently dropped. R11: no manual Approve is needed for either line to be posted or
   * for the unpostable one to be caught - untouched is a suggestion, same as approved.
   */
  it('names a plannable line that has no mirror, and leaves it out of the Confirm count', async () => {
    const board = twoLineOrder();
    getPlanningBoard.mockResolvedValue(
      withContribution(
        board,
        (entry) => entry.item_code === 'TPE-9204',
        (entry) => ({ ...entry, project_line_id: null }),
      ),
    );
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-a', ok: true, decision_revision: 1 }],
    });

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // UNTOUCHED, so it is COUNTED rather than named (R11): silence is agreement, so the
    // population that can be left out is every plannable line, and a notice naming hundreds
    // of them one by one is a wall nobody reads.
    expect(
      await screen.findByText(
        '1 untouched line is not on the planning record yet; open it to decide.',
      ),
    ).toBeInTheDocument();
    // `plannedLineCount` still counts it here: it cannot tell "adopted, but this one line's
    // mirror lags" from "not adopted at all", where the count DOES have to include a
    // not-yet-mirrored line (see "adopts, refetches, then posts..." below) - so the aggregate
    // reads 2 while the notice above still names the one line that will not post.
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (2)',
    );

    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    expect(confirmMany.mock.calls[0][0].orders[0].lines).toHaveLength(1);
  });

  /**
   * The other two ways a line cannot be posted used to be SILENT: the body left the line out
   * and the button said "Confirm 7 lines" beside eight verdicts, with nothing saying which one
   * was missing or why. Both are named now, and the count agrees.
   */
  it('names a plannable line whose Reserve the board cannot address, and leaves it out', async () => {
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
            {
              kind: 'reserve' as const,
              qty: '100',
              location: 'BRW-BB',
              reason: 'Covered.',
            },
          ],
        }),
      ),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      await screen.findByText(
        '1 untouched line reserves at a warehouse the board cannot address; open it to decide.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (1)',
    );
  });

  it('names an approved-as-is Buy of a discontinued product that carries no reason, and leaves it out', async () => {
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
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      await screen.findByText(
        '1 untouched line buys a discontinued product with no reason given; open it to decide.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (1)',
    );
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
      {
        ...board,
        orders: board.orders.map((order) => ({
          ...order,
          project_sales_order_id: null,
        })),
      },
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

  async function openConfirmDialog() {
    fireEvent.click(await screen.findByTestId('board-confirm'));
    await screen.findByRole('alertdialog');
  }

  it('offers Confirm on an order nobody has adopted, and never says planning has not started', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // R11: both plannable lines post as their own suggestion, no manual Approve needed.
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (2)',
    );
    expect(screen.getByTestId('board-confirm')).toBeEnabled();
    expect(
      screen.queryByText('Nobody has started planning this sales order yet.'),
    ).not.toBeInTheDocument();
  });

  it('adopts, refetches, then posts the body built from the ids that arrived', async () => {
    getPlanningBoard
      .mockResolvedValueOnce(unadopted())
      .mockResolvedValue(adopted());
    adoptSalesOrder.mockResolvedValue({
      project_sales_order_id: 'pso-so-a',
      so_number: 'SO403340',
      review_state: 'needs_cs_review',
      already_adopted: false,
    });
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-a', ok: true, decision_revision: 1 }],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(adoptSalesOrder).toHaveBeenCalledWith('so-a'));
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const [body] = confirmMany.mock.calls[0];
    // Built from the REFETCHED board: guessing an id before the mirror exists names nothing.
    expect(body.orders).toEqual([
      expect.objectContaining({
        pso_id: 'pso-so-a',
        lines: expect.arrayContaining([
          expect.objectContaining({ project_line_id: 'pl-so-a-1' }),
          expect.objectContaining({ project_line_id: 'pl-so-a-2' }),
        ]),
      }),
    ]);
  });

  it('does not adopt an order that already has a planning record', async () => {
    getPlanningBoard.mockResolvedValue(adopted());
    confirmMany.mockResolvedValue({
      results: [{ pso_id: 'pso-so-a', ok: true, decision_revision: 2 }],
    });

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    expect(adoptSalesOrder).not.toHaveBeenCalled();
  });

  it('says so when adoption fails, and confirms nothing', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());
    adoptSalesOrder.mockRejectedValue(
      new Error('Another planning record already holds SO403340.'),
    );

    renderPanel(['SO403340']);
    await openConfirmDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(adoptSalesOrder).toHaveBeenCalledWith('so-a'));
    expect(confirmMany).not.toHaveBeenCalled();
    // Nothing was committed, so the work is still the planner's.
    expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
      '2 to confirm · 0 rejected',
    );
  });

  it('shows no unmirrored notice on an order that was simply never adopted', async () => {
    getPlanningBoard.mockResolvedValue(unadopted());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    // That notice is for a mirror that is genuinely missing a line, which is a different
    // problem with a different fix. On a not-yet-adopted order it would name every line.
    expect(
      screen.queryByText(/not on the planning record yet/),
    ).not.toBeInTheDocument();
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
      demand({
        line_no: 1,
        item_code: 'WESERP10B',
        product_name: 'Wall socket 10A white',
      }),
      demand({
        line_no: 2,
        item_code: 'TPE-9204',
        product_name: 'Trunking 92mm',
      }),
      demand({
        line_no: 3,
        item_code: 'CKS1050',
        product_name: 'Ceiling kit 50',
      }),
    ]);
  }

  function productRows() {
    return [
      ...screen
        .getByTestId('fulfilment-board-matrix')
        .querySelectorAll('tbody tr'),
    ].map((row) => row.querySelector('th')?.textContent ?? '');
  }

  async function searchFor(term: string) {
    const box = screen.getByPlaceholderText(
      'Search sales order, customer, project or product',
    );
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
    getPlanningBoard.mockResolvedValue({
      ...board,
      line_count: 161,
      past_line_count: 130,
    });

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    await searchFor('tpe');

    // The product filter narrows the GRID and nothing else: the selection sentence describes
    // what is being planned, not what a search is showing.
    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));
    expect(
      screen.getByText('Planning 2 sales orders together'),
    ).toBeInTheDocument();
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

    expect(
      screen.getByPlaceholderText(
        'Search sales order, customer, project or product',
      ),
    ).toHaveValue('ceiling');
    await waitFor(() => expect(productRows()).toEqual(['CKS1050']));
  });

  it('clears with the X, and the whole board comes back', async () => {
    getPlanningBoard.mockResolvedValue(catalogue());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await searchFor('tpe');
    await waitFor(() => expect(productRows()).toEqual(['TPE-9204']));

    fireEvent.click(
      screen.getByRole('button', { name: 'Clear search' }),
    );

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
      withPolicy({
        name: 'Fair weighting',
        is_preview: false,
        discriminates_nothing: false,
      }),
    );

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    expect(getPlanningBoard).toHaveBeenCalledWith(
      ['SO403340'],
      'week',
      false,
      {},
    );
  });

  it('prints no policy identifiers anywhere above the grid', async () => {
    getPlanningBoard.mockResolvedValue(
      withPolicy({
        name: 'Fair weighting',
        factors: {
          need_by_date: 3,
          document_age: 1,
          customer_credit: 1,
          demand_class: 0,
        },
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
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'month',
        false,
        {},
      ),
    );
    expect(screen.getByLabelText('granularity')).toHaveValue('month');
  });

  it('falls back to week on a granularity nobody defined', async () => {
    currentSearchParams = new URLSearchParams('granularity=fortnightly');
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(
        ['SO403340'],
        'week',
        false,
        {},
      ),
    );
  });

  it('writes the granularity back when the planner turns the control', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.change(screen.getByLabelText('granularity'), {
      target: { value: 'month' },
    });

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

    expect(
      screen.queryByText(/has nothing to plan on this board/),
    ).not.toBeInTheDocument();
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
    return [
      ...screen
        .getByTestId('fulfilment-board-matrix')
        .querySelectorAll('tbody tr'),
    ].map((row) => (row.querySelector('th')?.textContent ?? '').trim());
  }

  async function pivotTo(value: string) {
    fireEvent.change(screen.getByLabelText('rows'), { target: { value } });
    await waitFor(() =>
      expect(screen.getByLabelText('rows')).toHaveValue(value),
    );
  }

  it('offers the four axes, product first', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    const select = screen.getByLabelText('rows');
    for (const label of ['Product', 'Sales order', 'Customer', 'Project']) {
      expect(
        within(select).getByRole('option', { name: label }),
      ).toBeInTheDocument();
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
    await waitFor(() =>
      expect(rowHeaders()).toEqual(['ALPHA SDN BHD', 'ZULU SDN BHD']),
    );

    await pivotTo('project');
    await waitFor(() => expect(rowHeaders()).toEqual(['TOWER A', 'TOWER Z']));
  });

  it('opens the same breakdown from a pivoted cell, with the same lines', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    await pivotTo('sales_order');

    fireEvent.click(
      await screen.findByRole('button', {
        name: /SO000001, 30 across 1 sales order/,
      }),
    );
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    // The Contributing lines tab lists LINES, which is what the dialog always listed.
    // Scoped to the dialog because the board itself is a table too.
    openLinesTab();
    const dialog = await screen.findByRole('dialog');
    const table = within(dialog).getByRole('table');
    expect(table.querySelectorAll('tbody tr')).toHaveLength(2);
    expect(table.textContent).toContain('AAA');
    expect(table.textContent).toContain('BBB');
  });

  it('keeps a decision made under one axis visible under another', async () => {
    getPlanningBoard.mockResolvedValue(twoOrders());

    renderPanel(['SO000001', 'SO000002']);
    await screen.findByTestId('fulfilment-board-matrix');

    // Decide a line while the rows are products. BBB is owed by one order only, so the cell
    // holds exactly the line this test is deciding. Rejected, not approved: under R11 an
    // approval leaves the board-wide counter unchanged (silence already agreed with it), so
    // only a rejection gives this test a number that actually moves.
    fireEvent.click(
      await screen.findByRole('button', {
        name: /BBB, 20 across 1 sales order/,
      }),
    );
    openLinesTab();
    fireEvent.click(screen.getByText('SO000001'));
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'The tower plan changed.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    closeDialog();
    await waitFor(() =>
      expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
        '2 to confirm · 1 rejected',
      ),
    );

    // ...and it is still the same line's decision when the rows become sales orders: the
    // aggregate stays the count, and the row itself still reads Rejected under the pivot.
    await pivotTo('sales_order');
    expect(screen.getByTestId('board-confirm-summary')).toHaveTextContent(
      '2 to confirm · 1 rejected',
    );

    fireEvent.click(
      await screen.findByRole('button', { name: /30 across 1 sales order/ }),
    );
    openLinesTab();
    const bbbRow = screen.getByText('Line 2').closest('tr') as HTMLElement;
    expect(within(bbbRow).getByText('Rejected')).toBeInTheDocument();
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
    fireEvent.change(
      screen.getByPlaceholderText(
        'Search sales order, customer, project or product',
      ),
      {
        target: { value: 'zulu' },
      },
    );

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

    fireEvent.change(
      screen.getByPlaceholderText(
        'Search sales order, customer, project or product',
      ),
      {
        target: { value: 'SO000002' },
      },
    );

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
/**
 * NO APPROVE ALL, NO CONFIRM ALL APPROVED (R11, UAC D1). Silence on a plannable line already
 * agrees with the suggestion, so there is nothing left for a bulk "approve everything" to do,
 * and the header carries one Confirm rather than a second all-approved button beside it. What
 * survives from the old flow - one `confirmMany` call grouped per order, a per-order result,
 * and a selection- not window-scoped population - is exercised through the single Confirm (N).
 */
describe('FulfilmentBoardPanel: one Confirm, not Approve all (D1, D4)', () => {
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

  it('carries no Approve all and no Confirm all approved button anywhere', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      screen.queryByRole('button', { name: 'Approve all' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Confirm all approved' }),
    ).not.toBeInTheDocument();
  });

  it('opens the confirm dialog naming how many lines across how many orders (D4)', async () => {
    getPlanningBoard.mockResolvedValue(twoUndecidedOrders());

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    // Both lines are already suggestions nobody has touched (R11): Confirm (2) from the start.
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (2)',
    );

    fireEvent.click(screen.getByTestId('board-confirm'));

    expect(
      await screen.findByText('Confirm 2 lines across 2 orders?'),
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
    fireEvent.click(screen.getByTestId('board-confirm'));
    await screen.findByText('Confirm 2 lines across 2 orders?');

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const body = confirmMany.mock.calls[0][0] as {
      orders: { pso_id: string; lines: { project_line_id: string }[] }[];
    };
    expect(body.orders).toHaveLength(2);
    const byPsoId = new Map(body.orders.map((order) => [order.pso_id, order]));
    expect(
      byPsoId.get('pso-so-a')?.lines.map((line) => line.project_line_id),
    ).toEqual(['pl-so-a-1']);
    expect(
      byPsoId.get('pso-so-b')?.lines.map((line) => line.project_line_id),
    ).toEqual(['pl-so-b-1']);

    expect(
      await screen.findByText('1 of 2 orders confirmed'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'SO403340: confirmed as revision 1 (0 purchase rows handed over)',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'SO398322: This line is not on this sales order any more.',
      ),
    ).toBeInTheDocument();
  });

  it('leaves Confirm disabled at Confirm (0) once the one plannable line is rejected', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.getByTestId('board-confirm')).toBeEnabled();

    fireEvent.click(
      await screen.findByRole('button', {
        name: /WESERP10B, 100 across 1 sales order/,
      }),
    );
    openLinesTab();
    fireEvent.click(screen.getByText('SO403340'));
    fireEvent.change(screen.getByLabelText(/^Why this differs/), {
      target: { value: 'Cancelled by the customer.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }));
    closeDialog();

    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (0)',
    );
    expect(screen.getByTestId('board-confirm')).toBeDisabled();
  });

  /**
   * BLOCKER (review, still true under the single Confirm): at day granularity `cells` only
   * covers the visible 30-day window (`DAY_WINDOW_COLUMNS`), so a line dated outside it is
   * invisible to `cells` - the panel has to read the server's top-level `contributions` for
   * the count AND for the body Confirm posts, or a line the window scrolled past is silently
   * left out of both.
   */
  it('confirms a line the day window has scrolled away from, not only the ones on screen', async () => {
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
    confirmMany.mockResolvedValue({
      results: [
        { pso_id: 'pso-so-a', ok: true, decision_revision: 1 },
        { pso_id: 'pso-so-b', ok: true, decision_revision: 1 },
      ],
    });

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    // The counter reads both lines, not only the one the window shows.
    expect(screen.getByTestId('board-confirm')).toHaveTextContent(
      'Confirm (2)',
    );

    fireEvent.click(screen.getByTestId('board-confirm'));
    expect(
      await screen.findByText('Confirm 2 lines across 2 orders?'),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(confirmMany).toHaveBeenCalledTimes(1));
    const body = confirmMany.mock.calls[0][0] as {
      orders: { pso_id: string }[];
    };
    expect(body.orders.map((order) => order.pso_id).sort()).toEqual([
      'pso-so-a',
      'pso-so-b',
    ]);
  });
});

/**
 * AC-C5 (retired 26 August 2026): NO legend row, and NO "already past" banner. The decision
 * strip's cards carry every label in its own colour, and the column headers already say
 * "Already past" over the periods they mean - so both were the screen restated in words.
 */
/**
 * Undo all throws away every decision taken since the board was opened and there is no way
 * back to them, so it asks first, with the count - PRINCIPLES: never one click, never
 * `confirm()`.
 */
describe('FulfilmentBoardPanel: Undo all asks first (D2)', () => {
  async function decideOneLineInTheList() {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));
    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');
    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    // The list's own rows: click one to open its decision panel, then Save the suggestion it
    // opens on, which is the approval.
    fireEvent.click(await screen.findByText('WESERP10B'));
    fireEvent.click(await screen.findByRole('button', { name: 'Save decision' }));
  }

  it('opens a confirmation naming how many drafts would go, and keeps them on Cancel', async () => {
    await decideOneLineInTheList();

    fireEvent.keyDown(screen.getByRole('button', { name: 'Board actions' }), {
      key: 'Enter',
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Undo all' }));

    expect(await screen.findByRole('alertdialog')).toHaveTextContent(
      'Discard 1 draft decision?',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Keep them' }));
    await waitFor(() =>
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument(),
    );
    // Saved (S4, R-F), not Approved: the pill reads the plain word once a decision exists.
    expect(await screen.findByTestId(/^decision-pill-/)).toHaveTextContent(
      'Saved',
    );
  });

  it('clears every draft decision once the discard is confirmed', async () => {
    await decideOneLineInTheList();

    fireEvent.keyDown(screen.getByRole('button', { name: 'Board actions' }), {
      key: 'Enter',
    });
    fireEvent.click(await screen.findByRole('menuitem', { name: 'Undo all' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));

    await waitFor(() =>
      expect(screen.getByTestId(/^decision-pill-/)).toHaveTextContent(
        'Suggested',
      ),
    );
  });
});

/**
 * A planning change already applied to ONE sales order is not applied to it twice (AC-P3-4).
 * The board-wide block only reads `applied_at` on the batch itself, which is set by the LAST
 * press, so without this an order whose own rows already read applied went back up with the
 * next one.
 */
describe('FulfilmentBoardPanel: an order whose change is already applied is not sent again', () => {
  it('leaves it out of the post and says so in the results', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));
    getPlanningChangeBatch.mockResolvedValue({
      id: 'pcb-1',
      applied_at: null,
      applied_by_name: null,
      orders: [
        {
          so_number: 'SO403340',
          rows: [{ id: 'pcr-1', applied_state: 'applied' }],
        },
      ],
    });

    renderPanel(['SO403340'], vi.fn(), 'pcb-1');
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByTestId('board-confirm'));
    fireEvent.click(await screen.findByRole('button', { name: 'Confirm' }));

    expect(
      await screen.findByText(
        /This planning change was already applied to this sales order\./,
      ),
    ).toBeInTheDocument();
    expect(confirmMany).not.toHaveBeenCalled();
  });
});

/**
 * The notice beside the button (R11): a line the planner composed is NAMED, capped at five,
 * and the lines nobody touched are counted - there can be hundreds of those, and a wall of
 * names is read by nobody.
 */
describe('unpostableNotices', () => {
  function line(lineNo: number, touched: boolean) {
    return {
      contribution: {
        item_code: 'TPE-9204',
        line_no: lineNo,
      } as unknown as BoardContribution,
      reason: 'buy_reason_missing' as const,
      touched,
    };
  }

  it('names a touched line and states the fix', () => {
    expect(unpostableNotices('buy_reason_missing', [line(2, true)])).toEqual([
      'TPE-9204 line 2 buys a discontinued product with no reason given, so this confirmation leaves it out. Amend it to give one.',
    ]);
  });

  it('caps the names at five and counts the rest', () => {
    const [sentence] = unpostableNotices(
      'buy_reason_missing',
      [1, 2, 3, 4, 5, 6, 7].map((no) => line(no, true)),
    );
    expect(sentence).toContain('line 5 and 2 more');
    expect(sentence).not.toContain('line 6');
  });

  it('counts untouched lines instead of naming them, in one sentence', () => {
    expect(
      unpostableNotices(
        'buy_reason_missing',
        [1, 2, 3].map((no) => line(no, false)),
      ),
    ).toEqual([
      '3 untouched lines buy a discontinued product with no reason given; open them to decide.',
    ]);
  });

  it('says both when the reason catches touched and untouched lines together', () => {
    expect(
      unpostableNotices('no_mirror', [line(2, true), line(3, false)]).length,
    ).toBe(2);
  });
});

describe('FulfilmentBoardPanel: what was taken off the page', () => {
  it('shows no legend row on either view', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');
    expect(screen.queryByTestId('supply-legend')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    await waitFor(() =>
      expect(
        screen.queryByTestId('fulfilment-board-matrix'),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByTestId('supply-legend')).not.toBeInTheDocument();
  });

  it('shows no "already past" banner, and the strip still carries the labels', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();
    await screen.findByTestId('fulfilment-board-matrix');

    expect(
      screen.queryByText(/lines are already past their delivery date/),
    ).toBeNull();
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
          {
            kind: 'buy',
            rung: 'buy',
            qty: '71',
            location: null,
            reason: 'Bought, as confirmed.',
          },
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
    expect(
      screen.getByTestId('decision-strip-changed-shared'),
    ).toBeInTheDocument();

    const buy = screen.getByTestId('decision-strip-buy');
    expect(within(buy).getByText('71')).toBeInTheDocument();
    expect(
      screen.getByTestId('decision-strip-changed-buy'),
    ).toBeInTheDocument();
  });

  it('sits above whichever view is on screen', async () => {
    getPlanningBoard.mockResolvedValue(amendedBoard());

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    const strip = screen.getByTestId('decision-strip');
    const matrix = screen.getByTestId('fulfilment-board-matrix');
    expect(strip.compareDocumentPosition(matrix)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
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
        expect(
          screen.getByTestId('fulfilment-board-matrix'),
        ).toBeInTheDocument();
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
    // its place, because it stands for a step of the ladder's walk and a card that came
    // and went would move every card beside it.
    expect(screen.getByTestId('decision-strip-borrow_order')).toBeDisabled();
    expect(screen.getByTestId('decision-strip-buy')).not.toBeDisabled();
    // The same is true of the two steps split out on 30 August 2026: the group's water and
    // the document borrow. `borrow_incoming` reads 0 on every board until S4 lands its
    // candidates, and it is rendered anyway - a step nobody can see is a step nobody knows
    // was asked.
    expect(screen.getByTestId('decision-strip-incoming')).toBeInTheDocument();
    expect(screen.getByTestId('decision-strip-borrow_incoming')).toBeDisabled();
    // `borrow_other` is the exception (re-ruled 30 August 2026): it is not a step, it is
    // the retired `cross_group_borrow` a decision frozen under an older ladder carries, so
    // at 0 / 0 it is not shown at all.
    expect(
      screen.queryByTestId('decision-strip-borrow_other'),
    ).not.toBeInTheDocument();
  });
});
