/**
 * S2 - the Stock Debt board (AC-S2-10, AC-S2-11, AC-S2-12).
 *
 * The columns ARE the payload: the axis, the TBA header and every balance come from the
 * envelope, so the tests here are mostly about the screen NOT inventing an axis of its own.
 * The arithmetic lives in `supply_assignment` and is not re-derived.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockDebtListResponse, StockDebtRow } from '../types/stockDebt.types';

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

// The real column-preferences hook runs here on purpose: the board passes
// `listingKey={null}`, and the point of the last test below is that the hook then reads
// nothing. The service underneath is mocked with a config a real user had saved under the
// pathname fallback, so a board that persisted would be caught reordering itself.
vi.mock('@/lib/listing-column-preferences/listColumnPreferencesService', () => ({
  getUserListColumnConfig: vi.fn(),
  upsertUserListColumnConfig: vi.fn(),
  resetUserListColumnConfig: vi.fn(),
}));

import { getUserListColumnConfig } from '@/lib/listing-column-preferences/listColumnPreferencesService';

const getStockDebtList = vi.fn();
const getStockDebtCell = vi.fn();

vi.mock('../services/stockDebtService', () => ({
  getStockDebtList: (...args: unknown[]) => getStockDebtList(...args),
  getStockDebtCell: (...args: unknown[]) => getStockDebtCell(...args),
}));

import { StockDebtClient } from './StockDebtClient';

function row(overrides: Partial<StockDebtRow> = {}): StockDebtRow {
  return {
    product_id: 'p1',
    product_code: 'SRTWB242',
    product_name: 'Sorento basin 242',
    months: [
      { key: '2026-08', balance: 55, tone: 'green' },
      { key: '2026-09', balance: -16, tone: 'red' },
      { key: '2026-10', balance: -652, tone: 'amber' },
    ],
    tba: -100,
    undated: -12,
    unlocated: -7,
    ...overrides,
  };
}

function envelope(rows: StockDebtRow[] = [row()]): StockDebtListResponse {
  return {
    data: rows,
    pagination: { total: rows.length, page: 1, limit: 25 },
    months: ['2026-08', '2026-09', '2026-10'],
    tba_month: '2030-01',
    groups: ['BB', 'IB'],
  };
}

function renderBoard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <StockDebtClient />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  getStockDebtList.mockResolvedValue(envelope());
  getStockDebtCell.mockResolvedValue({ demand: [], supply: [] });
  vi.mocked(getUserListColumnConfig).mockResolvedValue({
    listing_key: '/project-sales/stock-debt',
    config: { version: 1, columnOrder: ['product', 'tba', 'undated'] },
  });
});

describe('StockDebtClient', () => {
  it('opens on the products in debt, not on the whole catalogue', async () => {
    renderBoard();

    await waitFor(() =>
      expect(getStockDebtList).toHaveBeenCalledWith(
        expect.objectContaining({ onlyDebt: true, group: '', query: '' }),
      ),
    );
  });

  it('shows skeleton rows while the board loads, not an empty table', () => {
    getStockDebtList.mockReturnValue(new Promise(() => {}));

    const { container } = renderBoard();

    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
    expect(screen.queryByText('No product is in debt')).not.toBeInTheDocument();
  });

  it('says nothing is in debt and offers the whole book, which flips the toggle', async () => {
    getStockDebtList.mockResolvedValue(envelope([]));

    renderBoard();

    expect(await screen.findByText('No product is in debt')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Show every product' }));

    await waitFor(() =>
      expect(getStockDebtList).toHaveBeenLastCalledWith(
        expect.objectContaining({ onlyDebt: false }),
      ),
    );
  });

  it('states a load failure in the server words, with a Retry that asks again', async () => {
    getStockDebtList.mockRejectedValue(new Error('Stock debt is unavailable'));

    renderBoard();

    expect(
      await screen.findByText('Stock debt could not be loaded'),
    ).toBeInTheDocument();
    expect(screen.getByText('Stock debt is unavailable')).toBeInTheDocument();

    // The hook retries once of its own accord, so the count before the press is not 1.
    const before = getStockDebtList.mock.calls.length;
    getStockDebtList.mockResolvedValue(envelope());
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() =>
      expect(getStockDebtList.mock.calls.length).toBeGreaterThan(before),
    );
    expect(await screen.findByText('SRTWB242')).toBeInTheDocument();
  });

  it('takes its month columns from the payload, and the TBA header from tba_month', async () => {
    renderBoard();

    expect(await screen.findByText('Aug 26')).toBeInTheDocument();
    expect(screen.getByText('Sep 26')).toBeInTheDocument();
    expect(screen.getByText('Oct 26')).toBeInTheDocument();
    // The policy's own TBA month, never a hard-coded 2030.
    expect(screen.getByText('2030-01')).toBeInTheDocument();
    expect(screen.getByText('No date')).toBeInTheDocument();
    expect(screen.getByText('No location')).toBeInTheDocument();
    // A month the payload does not carry is not a column.
    expect(screen.queryByText('Nov 26')).not.toBeInTheDocument();
  });

  it('renders every cell as a press, signed, TBA and No date included', async () => {
    renderBoard();

    const surplus = await screen.findByRole('button', {
      name: 'SRTWB242, Aug 26, balance +55',
    });
    expect(surplus).toBeInTheDocument();
    expect(surplus).toHaveTextContent('+55');
    expect(
      screen.getByRole('button', { name: 'SRTWB242, Sep 26, balance -16' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'SRTWB242, 2030-01, balance -100' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'SRTWB242, No date, balance -12' }),
    ).toBeInTheDocument();
    // Demand booked at no warehouse. It draws nothing and sits in no month, so it is
    // stated here or it is silently missing from the one screen that lists what is owed.
    expect(
      screen.getByRole('button', { name: 'SRTWB242, No location, balance -7' }),
    ).toBeInTheDocument();
  });

  it('tones a month by what the payload says, and leaves TBA and No date untoned', async () => {
    renderBoard();

    const red = await screen.findByRole('button', {
      name: 'SRTWB242, Sep 26, balance -16',
    });
    expect(red.className).toContain('text-destructive');
    const amber = screen.getByRole('button', {
      name: 'SRTWB242, Oct 26, balance -652',
    });
    expect(amber.className).toContain('amber');
    // TBA draws no supply at all (R14), so a colour that means "can this still be bought in
    // time" would answer a question nobody asked of it.
    const tba = screen.getByRole('button', {
      name: 'SRTWB242, 2030-01, balance -100',
    });
    expect(tba.className).toContain('bg-muted');
    expect(tba.className).not.toContain('destructive');
  });

  it('opens the drill on the cell that was pressed', async () => {
    renderBoard();

    fireEvent.click(
      await screen.findByRole('button', { name: 'SRTWB242, Sep 26, balance -16' }),
    );

    // The board's own group narrowing travels with the drill, so the two foot: '' here is
    // the unnarrowed board. `StockDebtCellDialog.test.tsx` pins the narrowed case, and
    // `stockDebtService.test.ts` pins what it puts on the wire.
    await waitFor(() =>
      expect(getStockDebtCell).toHaveBeenCalledWith('p1', '2026-09', ''),
    );
    expect(await screen.findByTestId('stock-debt-cell-dialog')).toBeInTheDocument();
  });

  it('pins the product column through the grid, not through a class that loses', async () => {
    const { container } = renderBoard();
    await screen.findByText('SRTWB242');

    // `position: sticky` as an INLINE style is the whole point: a `sticky left-0` utility
    // sits in the same Tailwind position group as the `relative` the base cell carries, and
    // the stylesheet order decided which won - it computed to `relative` in the browser.
    const pinned = container.querySelectorAll('[data-pinned="left"]');
    expect(pinned.length).toBeGreaterThan(0);
    pinned.forEach((element) => {
      expect((element as HTMLElement).style.position).toBe('sticky');
      expect((element as HTMLElement).style.left).toBe('0px');
    });
  });

  it('keeps the calendar as the axis when the board arrives after the columns are built', async () => {
    // The list resolves AFTER mount, so at mount the only columns are Product and the three
    // that carry no supply. That snapshot is exactly what a persisted order used to be
    // reconciled against: TBA, No date and No location walked up next to Product and stayed
    // there, and every month column the board later built was warned about as non-existent.
    renderBoard();
    await screen.findByText('SRTWB242');

    expect(
      screen.getAllByRole('columnheader').map((cell) => cell.textContent?.trim()),
    ).toEqual([
      'Product',
      'Aug 26',
      'Sep 26',
      'Oct 26',
      '2030-01',
      'No date',
      'No location',
    ]);
    // The board is `listingKey={null}`, so there is no config to read in the first place.
    expect(getUserListColumnConfig).not.toHaveBeenCalled();
  });

  it('never prints the product id, only the code and the name', async () => {
    const { container } = renderBoard();

    await screen.findByText('SRTWB242');
    expect(screen.getByText('Sorento basin 242')).toBeInTheDocument();
    expect(container.textContent).not.toContain('p1');
  });
});
