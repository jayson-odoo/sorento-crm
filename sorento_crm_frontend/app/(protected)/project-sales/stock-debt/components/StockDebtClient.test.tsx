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
const exportStockDebt = vi.fn();

vi.mock('../services/stockDebtService', () => ({
  getStockDebtList: (...args: unknown[]) => getStockDebtList(...args),
  getStockDebtCell: (...args: unknown[]) => getStockDebtCell(...args),
  exportStockDebt: (...args: unknown[]) => exportStockDebt(...args),
  // The Export popover's own rows/sheets line (AC-33) is exercised in
  // `StockDebtExportPopover`'s own tests, not here - the board just needs the import
  // to resolve so it does not crash while mounting the popover.
  previewStockDebtExport: () => ({ rows: 0, sheets: 0 }),
}));

import { StockDebtClient } from './StockDebtClient';

function row(overrides: Partial<StockDebtRow> = {}): StockDebtRow {
  const base = {
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
    supplier_id: null,
    supplier_name: null,
    category_code: null,
    ...overrides,
  };
  // AC-5: sums months + tba + undated + unlocated - kept derived here rather than
  // hard-coded, so an override to any one field cannot silently leave `total` stale.
  const total =
    base.months.reduce((sum, month) => sum + month.balance, 0) +
    base.tba +
    base.undated +
    base.unlocated;
  return { ...base, total: overrides.total ?? total };
}

function envelope(rows: StockDebtRow[] = [row()]): StockDebtListResponse {
  const totalsMonths: Record<string, number> = {};
  ['2026-08', '2026-09', '2026-10'].forEach((key) => {
    totalsMonths[key] = rows.reduce(
      (sum, r) => sum + (r.months.find((m) => m.key === key)?.balance ?? 0),
      0,
    );
  });
  return {
    data: rows,
    pagination: { total: rows.length, page: 1, limit: 25 },
    months: ['2026-08', '2026-09', '2026-10'],
    tba_month: '2030-01',
    groups: ['BB', 'IB'],
    totals: {
      months: totalsMonths,
      tba: rows.reduce((sum, r) => sum + r.tba, 0),
      undated: rows.reduce((sum, r) => sum + r.undated, 0),
      unlocated: rows.reduce((sum, r) => sum + r.unlocated, 0),
      total: rows.reduce((sum, r) => sum + r.total, 0),
    },
    suppliers: [],
    sheet_counts: { supplier: 0, category: 0, supplier_category: 0 },
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

    // The board's own group/cutoff/book narrowing travels with the drill, so the two
    // foot: '' and the defaults here are the unnarrowed board.
    // `StockDebtCellDialog.test.tsx` pins the narrowed case, and `stockDebtService.
    // real.test.ts` pins what it puts on the wire.
    await waitFor(() =>
      expect(getStockDebtCell).toHaveBeenCalledWith('p1', '2026-09', '', undefined, 'all'),
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
      'Total',
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

  it('opens the drill on a real pointerdown -> pointerup -> click at one cell, and leaves nothing selected (AC-25, browser-pass finding)', async () => {
    // `it('opens the drill on the cell that was pressed', ...)` above only fires a bare
    // `click` - it never runs `onCellPointerDown` at all, so it cannot catch a defect that
    // lives in the INTERACTION between the pointerdown's optimistic single-cell select and
    // the click's own decision. A real browser click is always pointerdown -> pointerup ->
    // click at the same coordinates, which is what this dispatches.
    renderBoard();
    const cellButton = await screen.findByRole('button', {
      name: 'SRTWB242, Sep 26, balance -16',
    });

    fireEvent.pointerDown(cellButton, { button: 0, clientX: 10, clientY: 10 });
    fireEvent.pointerUp(cellButton, { button: 0, clientX: 10, clientY: 10 });
    fireEvent.click(cellButton, { button: 0, clientX: 10, clientY: 10 });

    await waitFor(() =>
      expect(getStockDebtCell).toHaveBeenCalledWith('p1', '2026-09', '', undefined, 'all'),
    );
    expect(await screen.findByTestId('stock-debt-cell-dialog')).toBeInTheDocument();
    // A plain click's own branch calls `clear()` - nothing should carry a selection ring
    // once the drill has opened.
    expect(cellButton.className).not.toMatch(/ring-1 ring-primary/);
  });

  it('grows the rectangle on a SECOND Shift+ArrowRight, focus moved to the new cell after the first (AC-32, browser-pass finding)', async () => {
    renderBoard();
    const first = await screen.findByRole('button', {
      name: 'SRTWB242, Aug 26, balance +55',
    });
    const second = screen.getByRole('button', {
      name: 'SRTWB242, Sep 26, balance -16',
    });
    const third = screen.getByRole('button', {
      name: 'SRTWB242, Oct 26, balance -652',
    });

    first.focus();
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(first, { key: 'ArrowRight', shiftKey: true });
    // The hook only returns the next coordinate; the CALLER (`StockDebtClient`) is the one
    // that must move DOM focus there (`cellRefs.current.get(...)?.focus()`, line ~308) so a
    // second consecutive key press has something focused to grow from.
    expect(document.activeElement).toBe(second);

    fireEvent.keyDown(second, { key: 'ArrowRight', shiftKey: true });
    expect(document.activeElement).toBe(third);

    expect(first.className).toMatch(/ring-1 ring-primary/);
    expect(second.className).toMatch(/ring-1 ring-primary/);
    expect(third.className).toMatch(/ring-1 ring-primary/);
  });
});
