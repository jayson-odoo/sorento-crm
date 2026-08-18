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

vi.mock('../../_shared/services/fulfilmentPlanningService', () => ({
  getPlanningBoard: (...args: unknown[]) => getPlanningBoard(...args),
  listFulfilmentPlanning: vi.fn(),
  getReconciliation: vi.fn(),
  rerunReconciliation: vi.fn(),
  adoptSalesOrder: vi.fn(),
  getSupply: vi.fn(),
  confirmSupply: vi.fn(),
  ConfirmSupplyError: class extends Error {},
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

import { FulfilmentBoardPanel } from './FulfilmentBoardPanel';
import {
  buildBoard,
  PREVIEW_POLICY,
  type BoardDemandLine,
} from '../../_shared/lib/fulfilmentBoard';

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

function boardOf(lines: BoardDemandLine[], freeStock: Record<string, string> = {}) {
  return buildBoard(lines, { today: TODAY, freeStock });
}

function renderPanel(soNumbers = ['SO403340', 'SO398322']) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FulfilmentBoardPanel soNumbers={soNumbers} onBack={vi.fn()} />
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

describe('FulfilmentBoardPanel: the axes', () => {
  it('pins Overdue first and No date last', async () => {
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
    expect(headers[1]).toContain('Overdue');
    expect(headers[headers.length - 1]).toContain('No date');
  });

  it('says how much of the selection is already past its required date', async () => {
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
    expect(screen.getByRole('button', { name: 'Confirm 1 lines' })).toBeEnabled();
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

describe('FulfilmentBoardPanel: the ranking policy (13.5)', () => {
  it('names the policy the board ranked by', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();

    expect(await screen.findByText("Today's rule (PO document sequence)")).toBeInTheDocument();
  });

  it('says plainly when the policy can rank nothing, rather than showing a plausible order', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel();

    expect(
      await screen.findByText(
        'This policy weights nothing a sales-order line carries, so every row scores the same and the ranking is flat.',
      ),
    ).toBeInTheDocument();
  });

  it('labels a previewed ranking as not live', async () => {
    const board = buildBoard([demand()], {
      today: TODAY,
      freeStock: {},
      policy: PREVIEW_POLICY,
    });
    getPlanningBoard.mockResolvedValue(board);

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
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'month', false),
    );
  });

  it('previews a fairer weighting without activating it', async () => {
    getPlanningBoard.mockResolvedValue(boardOf([demand()]));

    renderPanel(['SO403340']);
    await screen.findByTestId('fulfilment-board-matrix');

    fireEvent.click(screen.getByRole('button', { name: 'Preview a fairer weighting' }));

    await waitFor(() =>
      expect(getPlanningBoard).toHaveBeenCalledWith(['SO403340'], 'week', true),
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

  it('does not flash an empty or error state while loading', () => {
    getPlanningBoard.mockReturnValue(new Promise(() => {}));

    renderPanel();

    expect(
      screen.queryByText('These sales orders owe nothing that can be planned'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('The planning board could not be loaded')).not.toBeInTheDocument();
  });
});
