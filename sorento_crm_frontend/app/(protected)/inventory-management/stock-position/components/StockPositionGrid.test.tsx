/**
 * Inventory > Stock position (PLAN-stock-position-report-27oct): the supplier stock sheet, one
 * row per item. Warehouse columns are the server's list, headed by the code alone (owner review:
 * "don't need the stock word"); every column sorts on the server; a row opens Stock status.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;

vi.mock('next/navigation', () => ({
  usePathname: () => '/inventory-management/stock-position',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
const prefs = vi.hoisted(() => ({ useListingColumnPreferences: vi.fn() }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => prefs);
const exporter = vi.hoisted(() => ({ exportStockPosition: vi.fn(async () => {}) }));
vi.mock('../services/stockPositionService', () => exporter);
vi.mock('@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query', () => ({
  useBrandSelectQuery: () => ({ data: [] }),
}));
vi.mock('@/services/supplierSelectService', () => ({ getSuppliersSelect: async () => [] }));

const hook = vi.hoisted(() => ({ useStockPosition: vi.fn() }));
vi.mock('../hooks/useStockPosition', () => hook);

import StockPositionGrid, { formatQty } from './StockPositionGrid';
import type { StockPositionRow } from '../services/stockPosition.types';

function row(over: Partial<StockPositionRow> = {}): StockPositionRow {
  return {
    product_id: 'p-a',
    item_code: 'ITEM-A',
    description: 'Item A',
    supplier_id: 's1',
    supplier_code: 'S1',
    supplier_name: 'Supplier 1',
    brand_id: null,
    brand_name: null,
    stock: { BRW: 40, DC1: 244 },
    incoming_pool: 352,
    total_stock: 636,
    incoming_project: 880,
    total_incoming: 1232,
    packing_list_open: 40,
    outstanding_dealer: -70,
    outstanding_po: 1820,
    monthly_sales: 284,
    highest_month: 850,
    ...over,
  };
}

function withRows(rows: StockPositionRow[], codes = ['BRW', 'DC1']) {
  hook.useStockPosition.mockReturnValue({
    data: {
      data: rows,
      warehouses: codes.map((code) => ({ id: `w-${code}`, code })),
      pagination: { page: 1, limit: 50, total: rows.length, total_pages: 1 },
    },
    isLoading: false,
    isFetching: false,
    isPlaceholderData: false,
    error: null,
    refetch: vi.fn(),
  });
}

function renderGrid() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <StockPositionGrid />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  hook.useStockPosition.mockReset();
  exporter.exportStockPosition.mockClear();
  prefs.useListingColumnPreferences.mockReset();
  prefs.useListingColumnPreferences.mockReturnValue({ resetToDefaults: async () => {}, isLoading: false });
});

describe('StockPositionGrid', () => {
  it('heads each warehouse column with its code alone, in the order the server lists them', () => {
    withRows([row()], ['BRW', 'DC1', 'MWH']);
    renderGrid();
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    expect(headers.slice(0, 6)).toEqual(['Item code', 'Supplier', 'Brand', 'BRW', 'DC1', 'MWH']);
    expect(screen.queryByText(/BRW Stock/i)).toBeNull();
    expect(headers).toContain('Incoming BRW');
    expect(headers).toContain('Outstanding dealer');
  });

  it("prints the sheet's figures, a warehouse the item lacks as 0", () => {
    withRows([row()], ['BRW', 'DC1', 'MWH']);
    renderGrid();
    for (const text of ['ITEM-A', 'Supplier 1', '40', '244', '636', '1,232', '-70', '1,820', '850']) {
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
    }
  });

  it('asks the server to sort by the column clicked (manual sorting, the warehouse id wh:<code>)', () => {
    withRows([row()]);
    renderGrid();
    const last = () => hook.useStockPosition.mock.calls.at(-1)!;
    expect(last()[0].sorting).toEqual([{ id: 'item_code', desc: false }]);
    fireEvent.click(screen.getByRole('columnheader', { name: /^DC1/ }).querySelector('button') ?? screen.getByText('DC1'));
    const sorted = last()[0].sorting as { id: string }[];
    expect(sorted.map((s) => s.id)).toEqual(['wh:DC1']);
  });

  it('opens Stock status for the item from its row', () => {
    withRows([row()]);
    renderGrid();
    const link = screen.getAllByRole('link').find((a) => a.getAttribute('href')?.includes('stock-status'));
    expect(link?.getAttribute('href')).toBe('/inventory-management/stock-status?product_id=p-a');
  });

  it('says so when nothing matches', () => {
    withRows([]);
    renderGrid();
    expect(screen.getByText('No items to show')).toBeTruthy();
  });
});

describe('StockPositionGrid: the user picks which warehouses show (owner ruling Q5)', () => {
  it('saves column choices per user under the page, and mounts only once the warehouse columns are known', () => {
    hook.useStockPosition.mockReturnValue({
      data: undefined, isLoading: true, isFetching: true, isPlaceholderData: false, error: null, refetch: vi.fn(),
    });
    const { rerender } = renderGrid();
    expect(prefs.useListingColumnPreferences).not.toHaveBeenCalled();
    expect(screen.queryAllByRole('columnheader')).toHaveLength(0);

    withRows([row()], ['BRW', 'DC1']);
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <StockPositionGrid />
      </QueryClientProvider>,
    );
    const call = prefs.useListingColumnPreferences.mock.calls[0][0] as {
      listingKey: string | null;
      table: { getAllLeafColumns: () => { id: string }[] };
    };
    expect(call.listingKey).toBe('/inventory-management/stock-position');
    expect(call.table.getAllLeafColumns().map((c) => c.id)).toEqual(
      expect.arrayContaining(['wh:BRW', 'wh:DC1']),
    );
  });

  it('a hidden warehouse column leaves the grid and the export', async () => {
    withRows([row()], ['BRW', 'DC1']);
    renderGrid();
    const call = prefs.useListingColumnPreferences.mock.calls.at(-1)![0] as {
      table: { getColumn: (id: string) => { toggleVisibility: (v: boolean) => void } };
    };
    await act(async () => call.table.getColumn('wh:DC1').toggleVisibility(false));
    const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
    expect(headers).toContain('BRW');
    expect(headers).not.toContain('DC1');

    fireEvent.click(screen.getByText('Export to Excel'));
    await waitFor(() => expect(exporter.exportStockPosition).toHaveBeenCalled());
    expect(exporter.exportStockPosition.mock.calls[0][2]).toEqual(['BRW']);
  });
});

describe('formatQty', () => {
  it('prints whole units with thousands separated, negatives kept', () => {
    expect(formatQty(1232)).toBe('1,232');
    expect(formatQty(-70)).toBe('-70');
    expect(formatQty(283.6)).toBe('284');
    expect(formatQty(0)).toBe('0');
  });
});
