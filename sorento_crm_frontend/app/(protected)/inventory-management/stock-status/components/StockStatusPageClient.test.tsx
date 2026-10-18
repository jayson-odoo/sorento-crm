/**
 * STOCK-STATUS round 6 (owner 18 Oct 07:56, "1. Keep"; UAC AC-35): the stand-alone page draws the
 * same stock table, built from the AutoCount read alone.
 */
import React from 'react';
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
const useStockStatusMock = vi.fn((..._args: unknown[]) => ({ data: STATUS as unknown, isLoading: false }));
vi.mock('@/components/stock-status/useStockStatus', () => ({
  useStockStatus: (...args: unknown[]) => useStockStatusMock(...args),
}));

import StockStatusPageClient from './StockStatusPageClient';

beforeEach(() => {
  vi.clearAllMocks();
  search = 'product_id=prod-1';
});

describe('Stock status page, round 6', () => {
  it('draws the stock table from the AutoCount read alone', () => {
    render(<StockStatusPageClient />);
    const props = cellStockTableSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.locations).toEqual([]);
    expect(props.autoCount).toBe(STATUS);
  });

  it('asks for an item before any table', () => {
    search = '';
    render(<StockStatusPageClient />);
    expect(screen.queryByTestId('cell-stock-table')).not.toBeInTheDocument();
    expect(screen.getByText('Pick an item')).toBeInTheDocument();
  });
});
