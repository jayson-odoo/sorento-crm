import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { DataGridApiResponse } from '@/components/ui/data-grid';
import type { NetPositionRow } from '../types/scm.types';

// jsdom polyfills required by ScrollArea / DataGrid.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  usePathname: () => '/scm',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// DataGrid persists column prefs via this hook (fires network) - stub it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const useNetPosition = vi.fn();
vi.mock('../hooks/useScmDashboard', () => ({
  useNetPosition: (...a: unknown[]) => useNetPosition(...a),
}));

import { ProductPerspectiveGrid } from './ProductPerspectiveGrid';
import { EMPTY_SCM_FILTERS } from '../services/scmDashboardService';

function row(over: Partial<NetPositionRow>): NetPositionRow {
  return {
    sku: 'WESERP10B',
    product_name: 'Weber ERP 10B',
    product_class: null,
    variant: null,
    supplier_name: 'Amalgamated',
    on_hand: 0,
    on_order: 40,
    committed: 25,
    net_position: 15,
    stock_valuation: null,
    last_movement_at: null,
    status: 'stockout',
    imbalance: false,
    stockout_with_committed: true,
    attention_rank: 0,
    warehouses: [],
    avg_daily_demand: null,
    days_of_cover: null,
    abc_class: null,
    xyz_class: null,
    reorder_point: null,
    ...over,
  };
}

function result(data: NetPositionRow[]): DataGridApiResponse<NetPositionRow> {
  return { data, empty: data.length === 0, pagination: { total: data.length, page: 1 } };
}

const props = { filters: EMPTY_SCM_FILTERS, onToggleHealth: vi.fn() };

beforeEach(() => useNetPosition.mockReset());

describe('ProductPerspectiveGrid', () => {
  it('renders the error state', () => {
    useNetPosition.mockReturnValue({ data: undefined, isLoading: false, isFetching: false, isError: true, refetch: vi.fn() });
    render(<ProductPerspectiveGrid {...props} />);
    expect(screen.getByText(/Couldn't load net position/i)).toBeInTheDocument();
  });

  it('renders rows with the committed-stockout attention pill', () => {
    useNetPosition.mockReturnValue({
      data: result([row({})]),
      isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    render(<ProductPerspectiveGrid {...props} />);
    expect(screen.getByText('WESERP10B')).toBeInTheDocument();
    // attention badge on stockout-with-committed rows
    expect(screen.getByText('committed')).toBeInTheDocument();
  });

  it('renders "-" for the deferred demand columns', () => {
    useNetPosition.mockReturnValue({
      data: result([row({ stockout_with_committed: false, status: 'healthy' })]),
      isLoading: false, isFetching: false, isError: false, refetch: vi.fn(),
    });
    render(<ProductPerspectiveGrid {...props} />);
    // avg daily demand / days of cover / reorder point cells + null valuation +
    // last movement - all render the em-dash. At least the 3 deferred columns.
    expect(screen.getAllByText('-').length).toBeGreaterThanOrEqual(3);
  });
});
