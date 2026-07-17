import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

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

const useScmProducts = vi.fn();
vi.mock('../hooks/useScmDashboard', () => ({
  useScmProducts: () => useScmProducts(),
}));

import { RollupTiles } from './RollupTiles';
import { EMPTY_SCM_FILTERS } from '../services/scmDashboardService';
import type { ScmRollups } from '../types/scm.types';

const DATA: ScmRollups = {
  total_stock_valuation: 4_182_650,
  dead_stock_valuation: 318_400,
  stockout_count: 3,
  incoming_po_count: 5,
  incoming_po_next_eta: '2026-08-01',
  valuation_missing_cost_count: 1,
  below_rop_count: null,
  overstock_valuation: null,
  overstock_count: null,
};

const baseProps = {
  filters: EMPTY_SCM_FILTERS,
  onViewInList: vi.fn(),
  onToggleFilter: vi.fn(),
  activeStatus: null,
};

beforeEach(() => {
  useScmProducts.mockReturnValue({
    data: { data: [], total: 0, page: 1 },
    isLoading: false,
    isFetching: false,
    isError: false,
  });
  baseProps.onToggleFilter = vi.fn();
  baseProps.onViewInList = vi.fn();
});

describe('RollupTiles', () => {
  it('renders the error state', () => {
    render(<RollupTiles data={undefined} isLoading={false} isError {...baseProps} />);
    expect(screen.getByText(/Couldn't load roll-up figures/i)).toBeInTheDocument();
  });

  it('renders skeletons (no figures) while loading', () => {
    render(<RollupTiles data={undefined} isLoading isError={false} {...baseProps} />);
    expect(screen.queryByText('Out of stock')).not.toBeInTheDocument();
  });

  it('renders figures and shows "—" for the two deferred tiles', () => {
    render(<RollupTiles data={DATA} isLoading={false} isError={false} {...baseProps} />);
    expect(screen.getByText('Out of stock')).toBeInTheDocument();
    expect(screen.getByText('Low stock')).toBeInTheDocument();
    expect(screen.getByText('Overstock valuation')).toBeInTheDocument();
    // exactly the two deferred tiles render the em-dash
    expect(screen.getAllByText('—')).toHaveLength(2);
  });

  it('toggles a health filter from a stat card body', () => {
    render(<RollupTiles data={DATA} isLoading={false} isError={false} {...baseProps} />);
    fireEvent.click(screen.getByTitle('Filter to Out of stock'));
    expect(baseProps.onToggleFilter).toHaveBeenCalledWith('stockout');
  });

  it('opens the drill-down popup and lists the fetched products', () => {
    useScmProducts.mockReturnValue({
      data: {
        data: [
          {
            sku: 'CWCY605',
            product_name: 'Cement CY605',
            warehouse_code: 'WH-A',
            warehouse_name: 'Shah Alam',
            on_hand: 0,
            on_order: 0,
            committed: 12,
            net_position: -12,
            stock_valuation: null,
            status: 'stockout',
            stockout_with_committed: true,
          },
        ],
        total: 1,
        page: 1,
      },
      isLoading: false,
      isFetching: false,
      isError: false,
    });
    render(<RollupTiles data={DATA} isLoading={false} isError={false} {...baseProps} />);
    fireEvent.click(screen.getByLabelText(/Out of stock: 3\. View products/i));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('CWCY605')).toBeInTheDocument();
  });
});
