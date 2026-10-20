/**
 * STOCK-STATUS round 6 (owner 18 Oct 07:56, "1. Keep"; UAC AC-35): the stand-alone page draws the
 * same stock table, built from the AutoCount read alone.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

let search = 'product_id=prod-1';
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => '/inventory-management/stock-status',
  useSearchParams: () => new URLSearchParams(search),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: () => <div data-testid="item-picker" />,
}));
vi.mock('@/components/stock-status/stockStatusService', () => ({
  searchStockStatusProducts: vi.fn(),
}));

const cellStockTableSpy = vi.fn();
vi.mock('../../../project-sales/fulfilment-planning/components/CellStockTable', () => ({
  CellStockTable: (props: Record<string, unknown>) => {
    cellStockTableSpy(props);
    return <div data-testid="cell-stock-table" />;
  },
}));

const STATUS = { product_id: 'prod-1', item_code: 'SRTWB1515', locations: [], incoming_pl: [] };
const useStockStatusMock = vi.fn<(...args: unknown[]) => Record<string, unknown>>(() => ({ data: STATUS as unknown, isLoading: false }));
vi.mock('@/components/stock-status/useStockStatus', () => ({
  useStockStatus: (...args: unknown[]) => useStockStatusMock(...args),
}));

import StockStatusPageClient from './StockStatusPageClient';

beforeEach(() => {
  vi.clearAllMocks();
  search = 'product_id=prod-1';
  useStockStatusMock.mockReturnValue({ data: STATUS, isLoading: false });
});

describe('Stock status page, round 6', () => {
  it('draws the stock table from the AutoCount read alone', () => {
    render(<StockStatusPageClient />);
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.locations).toEqual([]);
    expect(props.autoCount).toBe(STATUS);
  });

  it('shows a skeleton while the read is out, and says so when it fails', () => {
    useStockStatusMock.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    const { unmount } = render(<StockStatusPageClient />);
    expect(screen.getByTestId('stock-status-loading')).toBeInTheDocument();
    unmount();
    useStockStatusMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<StockStatusPageClient />);
    expect(screen.getByText('The stock status could not be loaded')).toBeInTheDocument();
    expect(screen.queryByTestId('cell-stock-table')).not.toBeInTheDocument();
  });

  it('asks for an item before any table', () => {
    search = '';
    render(<StockStatusPageClient />);
    expect(screen.queryByTestId('cell-stock-table')).not.toBeInTheDocument();
    expect(screen.getByText('Pick an item')).toBeInTheDocument();
  });
});

describe('STOCK-GROUPBY (AC-20): the stand-alone page carries the Group by bar', () => {
  it('AC-20 the table the page draws, given the AutoCount read, shows the group-by-bar', async () => {
    const status = {
  product_id: 'prod-1',
  item_code: 'ITEM-1',
  locations: [{ warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', warehouse_name: 'BRW-BB', is_active: true, on_hand: 5, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 5 }],
  totals: { on_hand: 5, so_qty: 0, po_qty: 0, spo_qty: 0, forecast: 5, incoming_pl: 0, forecast_incl_pl: 5 },
  incoming_pl: [],
  sales_orders: [],
  purchase_orders: [],
  spos: [],
};
    useStockStatusMock.mockReturnValue({ data: status, isLoading: false });
    render(<StockStatusPageClient />);
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as React.ComponentProps<
      typeof import('../../../project-sales/fulfilment-planning/components/CellStockTable').CellStockTable
    >;
    expect(props.autoCount).toBe(status);
    const actual = await vi.importActual<
      typeof import('../../../project-sales/fulfilment-planning/components/CellStockTable')
    >('../../../project-sales/fulfilment-planning/components/CellStockTable');
    render(
      <QueryClientProvider client={new QueryClient()}>
        <actual.CellStockTable {...props} />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId('group-by-bar')).toBeInTheDocument();
  });
});
