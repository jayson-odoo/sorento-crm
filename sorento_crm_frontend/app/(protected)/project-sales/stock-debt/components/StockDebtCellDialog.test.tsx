/**
 * S2 - the cell drill (AC-S2-7, AC-S2-11, R28/R30/R31/R37).
 *
 * Two TABS behind one cell, and four sentences that are easy to get subtly wrong: Plan
 * hands the ORDER to the board, an overdue document says it counts as nothing, a PO's
 * bought-for date is stated as what it is and never as an arrival, and the two footers
 * foot with the cell that opened them (`Free` less `Uncovered` is the balance in the
 * title, R37).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
      short_qty: 0,
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
      short_qty: 16,
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
      free_qty: 0,
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
      free_qty: 0,
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

/** Radix's TabsTrigger switches on mouse down; a bare `click` leaves the old panel up. */
function switchTab(name: string) {
  const tab = screen.getByRole('tab', { name });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
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
    await screen.findByText('SO390918');
    switchTab('Supply (2)');

    expect(await screen.findByText('SPO 2026/09-0088')).toBeInTheDocument();
    expect(screen.getByText('SO407114 (40)')).toBeInTheDocument();
    // Nobody has it: "Free" rather than a blank cell, which reads as a missing figure.
    expect(screen.getByText('Free')).toBeInTheDocument();
  });

  it('says an overdue document counts as nothing, and only a PO says what it was bought for', async () => {
    renderDialog();
    await screen.findByText('SO390918');
    switchTab('Supply (2)');

    expect(await screen.findByText('overdue, not counted')).toBeInTheDocument();
    // R30: the PO's `expected_date` is the SO date it was typed against, so it is worded as
    // that and never as an arrival - and an SPO has no such date to state.
    expect(screen.getByText('bought for 15/10/2026')).toBeInTheDocument();
    expect(screen.queryByText(/bought for 12\/10\/2026/)).not.toBeInTheDocument();
  });

  it('renders each tab own empty state rather than a blank table', async () => {
    renderDialog({ demand: [], supply: [] });

    expect(await screen.findByText('Nothing is due here')).toBeInTheDocument();
    switchTab('Supply (0)');
    expect(await screen.findByText('Nothing arrives here')).toBeInTheDocument();
  });

  it('names the product, the column and the balance the reader pressed', async () => {
    renderDialog();

    const dialog = await screen.findByTestId('stock-debt-cell-dialog');
    // The SCM family's shell: `<Kind> · <code>` with the qualifier beside it, and the
    // product name on the muted line under it.
    expect(within(dialog).getByText('Product · SRTWB242')).toBeInTheDocument();
    // The month, the signed balance, and the group the board was narrowed to - so the
    // figures are not read as the whole book.
    expect(within(dialog).getByText('Oct 26 · -16 · BB group')).toBeInTheDocument();
    expect(within(dialog).getByText('Sorento basin 242')).toBeInTheDocument();
  });

  it('is two tabs, Demand first, each saying how many rows it holds', async () => {
    renderDialog();
    await screen.findByText('SO390918');

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Demand (2)', 'Supply (2)']);
    // Demand is what the reader came for: which orders go without.
    expect(tabs[0]).toHaveAttribute('data-state', 'active');
  });

  it('foots with the cell that opened it: Free less Uncovered is the balance (R37)', async () => {
    renderDialog();
    await screen.findByText('SO390918');

    // The short line went without 16 on its own date; nothing in the month is free, so the
    // cell reads -16 - which is the balance in the title.
    expect(screen.getByText('Uncovered 16')).toBeInTheDocument();
    switchTab('Supply (2)');
    expect(await screen.findByText('Free 0')).toBeInTheDocument();
  });

  it('states the short quantity a LATE line still books, although it ends fully assigned (R37)', async () => {
    // Gap case: a `late` line is one later supply cleared - `assigned_qty` equals
    // `open_qty` by the end of the walk - but it still went without ON ITS OWN DATE, and
    // `short_qty` is the server's own figure for that (re-deriving `open - assigned` gives
    // 0 for exactly this row, which is the defect R37's fixture correction exists to catch:
    // "the drill for those columns was empty" while the cell it opened from was in debt).
    renderDialog({
      demand: [
        {
          so_number: 'SO398214',
          agent_code: 'CYNDI',
          warehouse_code: 'BRW-BB',
          required_date: '2026-10-20',
          open_qty: 20,
          assigned_qty: 20,
          assigned_source: 'SPO 2026/09-0088',
          short_qty: 20,
          status: 'late',
        },
      ],
      supply: [],
    });

    expect(await screen.findByText('SO398214')).toBeInTheDocument();
    const row = screen.getByText('SO398214').closest('tr') as HTMLElement;
    // Fully assigned by the time the whole walk is over: Open and Assigned both read 20.
    expect(within(row).getAllByText('20')).toHaveLength(2);
    // ...but the status cell still states what it went without on its own date, not just
    // the word "late" with the figure that made it so left unsaid.
    expect(within(row).getByText('short 20')).toBeInTheDocument();
  });
});
