/**
 * S2 - the cell drill (AC-S2-7, AC-S2-11, R28/R30/R31).
 *
 * Two tables behind one cell, and three sentences that are easy to get subtly wrong: Plan
 * hands the ORDER to the board, an overdue document says it counts as nothing, and a PO's
 * bought-for date is stated as what it is and never as an arrival.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockDebtCell } from '../types/stockDebt.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/project-sales/stock-debt',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const getStockDebtCell = vi.fn();

vi.mock('../services/stockDebtService', () => ({
  getStockDebtList: vi.fn(),
  getStockDebtCell: (...args: unknown[]) => getStockDebtCell(...args),
}));

import { StockDebtCellDialog } from './StockDebtCellDialog';

const CELL: StockDebtCell = {
  demand: [
    {
      so_number: 'SO390918',
      agent_code: 'JENNIFER',
      warehouse_code: 'BRW-BB',
      required_date: '2026-10-15',
      open_qty: 12,
      assigned_qty: 12,
      assigned_source: 'On hand BRW-BB',
      status: 'covered',
    },
    {
      so_number: 'SO375875',
      agent_code: 'JAY',
      warehouse_code: 'MWH-BB',
      required_date: '2026-10-26',
      open_qty: 32,
      assigned_qty: 16,
      assigned_source: 'On hand BRW-BB',
      status: 'short',
    },
  ],
  supply: [
    {
      kind: 'spo',
      ref: 'SPO 2026/09-0088',
      warehouse_code: 'MWH-BB',
      date: '2026-10-12',
      bought_for: null,
      qty: 40,
      overdue: false,
      assigned_to: [{ so_number: 'SO407114', qty: 40 }],
    },
    {
      kind: 'po',
      ref: 'PO 202605-S0072 line 5',
      warehouse_code: 'BRW-BB',
      date: '2026-08-16',
      bought_for: '2026-10-15',
      qty: 12,
      overdue: true,
      assigned_to: [],
    },
  ],
};

function renderDialog(cell: StockDebtCell = CELL) {
  getStockDebtCell.mockResolvedValue(cell);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockDebtCellDialog
        productId="p1"
        productCode="SRTWB242"
        productName="Sorento basin 242"
        month="2026-10"
        monthLabel="Oct 26"
        balance={-16}
        group="BB"
        onClose={() => {}}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('StockDebtCellDialog', () => {
  it('asks for the cell it was opened on', async () => {
    renderDialog();
    await waitFor(() => expect(getStockDebtCell).toHaveBeenCalledWith('p1', '2026-10', 'BB'));
  });

  it('lists the demand with its bin, its due date and its status', async () => {
    renderDialog();

    expect(await screen.findByText('SO390918')).toBeInTheDocument();
    expect(screen.getByText('JENNIFER')).toBeInTheDocument();
    // The Bin column (AC-S2-7): which pile the line sits in decides everything else. Both
    // codes also appear in the Supply table, so the assertion is scoped to Demand's row.
    const shortRow = screen.getByText('SO375875').closest('tr') as HTMLElement;
    expect(within(shortRow).getByText('MWH-BB')).toBeInTheDocument();
    const coveredRow = screen.getByText('SO390918').closest('tr') as HTMLElement;
    expect(within(coveredRow).getByText('BRW-BB')).toBeInTheDocument();
    expect(screen.getByText('covered')).toBeInTheDocument();
    // A short line says HOW short, because the quantity is the thing to act on.
    expect(screen.getByText('short 16')).toBeInTheDocument();
  });

  it('hands the ORDER to the board on Plan, never the product', async () => {
    renderDialog();

    const links = await screen.findAllByRole('link', { name: 'Plan' });
    expect(links[0]).toHaveAttribute(
      'href',
      '/project-sales/fulfilment-planning?orders=SO390918',
    );
    expect(links[1]).toHaveAttribute(
      'href',
      '/project-sales/fulfilment-planning?orders=SO375875',
    );
  });

  it('lists the supply with its document, arrival and who holds it', async () => {
    renderDialog();

    expect(await screen.findByText('SPO 2026/09-0088')).toBeInTheDocument();
    expect(screen.getByText('SO407114 (40)')).toBeInTheDocument();
    // Nobody has it: "Free" rather than a blank cell, which reads as a missing figure.
    expect(screen.getByText('Free')).toBeInTheDocument();
  });

  it('says an overdue document counts as nothing, and only a PO says what it was bought for', async () => {
    renderDialog();

    expect(await screen.findByText('overdue, not counted')).toBeInTheDocument();
    // R30: the PO's `expected_date` is the SO date it was typed against, so it is worded as
    // that and never as an arrival - and an SPO has no such date to state.
    expect(screen.getByText('bought for 15/10/2026')).toBeInTheDocument();
    expect(screen.queryByText(/bought for 12\/10\/2026/)).not.toBeInTheDocument();
  });

  it('renders both empty states rather than two blank tables', async () => {
    renderDialog({ demand: [], supply: [] });

    expect(await screen.findByText('Nothing is due here')).toBeInTheDocument();
    expect(screen.getByText('Nothing arrives here')).toBeInTheDocument();
  });

  it('names the product, the column and the balance the reader pressed', async () => {
    renderDialog();

    const dialog = await screen.findByTestId('stock-debt-cell-dialog');
    expect(
      within(dialog).getByText('SRTWB242 - Sorento basin 242 · Oct 26'),
    ).toBeInTheDocument();
    expect(within(dialog).getByText('balance -16')).toBeInTheDocument();
    // The group the board was narrowed to, so the figures are not read as the whole book.
    expect(within(dialog).getByText('BB group')).toBeInTheDocument();
  });
});
