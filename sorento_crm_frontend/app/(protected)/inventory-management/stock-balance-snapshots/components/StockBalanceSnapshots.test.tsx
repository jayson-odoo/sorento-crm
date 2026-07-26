/**
 * StockBalanceSnapshots — read-only AutoCount stock-balance run mirror.
 *   - a run auto-selects and its rows render (resolved + unresolved product);
 *   - negative balance is shown with the destructive style;
 *   - the AutoCount provenance badge renders (read-only mirror);
 *   - empty (no runs synced) + loading states render without crashing.
 *
 * Data hooks are mocked; DataGrid's browser-only deps are stubbed inline.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

const mockUseRuns = vi.fn();
const mockUseRun = vi.fn();
const mockAnnotate = vi.fn();
vi.mock('../hooks/useStockBalance', () => ({
  useStockBalanceRuns: () => mockUseRuns(),
  useStockBalanceRun: (id: string | null) => mockUseRun(id),
  useAnnotateStockBalanceRun: () => mockAnnotate(),
}));

import StockBalanceSnapshots from './StockBalanceSnapshots';

const RUN = {
  id: 'run-1',
  captured_at: '2026-07-26T07:23:00',
  row_count: 2,
  source: 'autocount',
  internal_note: null,
  follow_up: false,
  created_at: '2026-07-26T07:23:00',
};

const ROWS = [
  {
    id: 'row-1',
    item_code: 'BRACD7799CP-ENG',
    product_id: 'p-1',
    product_name: 'BRACD7799CP-ENG',
    location_code: 'BRW-AM',
    warehouse_id: 'w-1',
    uom: 'PCS',
    batch_no: null,
    balance: '-5',
    smallest_bal_qty: null,
    standard_cost: null,
    total_cost: null,
    average_cost: '12.5',
    rate: null,
    description: null,
  },
  {
    id: 'row-2',
    item_code: 'PHANTOM-1',
    product_id: null,
    product_name: null,
    location_code: 'NOWHERE',
    warehouse_id: null,
    uom: 'PCS',
    batch_no: null,
    balance: '3',
    smallest_bal_qty: null,
    standard_cost: null,
    total_cost: null,
    average_cost: null,
    rate: null,
    description: null,
  },
];

beforeEach(() => {
  cleanup();
  mockUseRuns.mockReset();
  mockUseRun.mockReset();
  mockAnnotate.mockReset();
  mockAnnotate.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('StockBalanceSnapshots', () => {
  it('renders the selected run rows with the AutoCount badge', () => {
    mockUseRuns.mockReturnValue({
      data: { data: [RUN], pagination: { total: 1, page: 1, limit: 100 } },
      isLoading: false,
    });
    mockUseRun.mockReturnValue({ data: { ...RUN, rows: ROWS }, isLoading: false });

    render(<StockBalanceSnapshots />);
    // item_code + product_name cells both carry the code for the resolved row
    expect(screen.getAllByText('BRACD7799CP-ENG').length).toBeGreaterThan(0);
    expect(screen.getByText('PHANTOM-1')).toBeInTheDocument();
    // unresolved product renders an explicit placeholder
    expect(screen.getByText('Unresolved')).toBeInTheDocument();
    expect(screen.getByText('AutoCount')).toBeInTheDocument();
  });

  it('shows a negative balance with the destructive style', () => {
    mockUseRuns.mockReturnValue({
      data: { data: [RUN], pagination: { total: 1, page: 1, limit: 100 } },
      isLoading: false,
    });
    mockUseRun.mockReturnValue({ data: { ...RUN, rows: ROWS }, isLoading: false });

    render(<StockBalanceSnapshots />);
    const neg = screen.getByText('-5');
    expect(neg.className).toContain('text-destructive');
  });

  it('renders the empty state when no runs have synced', () => {
    mockUseRuns.mockReturnValue({
      data: { data: [], pagination: { total: 0, page: 1, limit: 100 } },
      isLoading: false,
    });
    mockUseRun.mockReturnValue({ data: undefined, isLoading: false });

    render(<StockBalanceSnapshots />);
    expect(screen.getByText('No snapshots have synced yet.')).toBeInTheDocument();
  });

  it('renders the loading state without crashing', () => {
    mockUseRuns.mockReturnValue({ data: undefined, isLoading: true });
    mockUseRun.mockReturnValue({ data: undefined, isLoading: false });

    render(<StockBalanceSnapshots />);
    expect(screen.getByText('Snapshot run')).toBeInTheDocument();
  });
});
