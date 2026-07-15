import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

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

const useScmProducts = vi.fn();
vi.mock('../hooks/useScmDashboard', () => ({
  useScmProducts: (...a: unknown[]) => useScmProducts(...a),
}));

import { ProductListDialog } from './ProductListDialog';
import { NET_POSITION_FORMULA } from './HealthIndicators';
import { EMPTY_SCM_FILTERS } from '../services/scmDashboardService';
import type { ProductSummary } from '../types/scm.types';

function prod(over: Partial<ProductSummary> = {}): ProductSummary {
  return {
    sku: 'CWCY605',
    product_name: 'Cement CY605',
    warehouse_code: 'WH-A',
    warehouse_name: 'Shah Alam',
    on_hand: 0,
    on_order: 40,
    committed: 12,
    net_position: 28,
    stock_valuation: 1500,
    status: 'stockout',
    stockout_with_committed: true,
    avg_daily_demand: null,
    days_of_cover: null,
    abc_class: null,
    xyz_class: null,
    ...over,
  };
}

function page(rows: ProductSummary[], total: number) {
  return { data: { data: rows, total, page: 1 }, isLoading: false, isFetching: false, isError: false };
}

const baseProps = {
  open: true,
  onOpenChange: vi.fn(),
  title: 'Stockouts',
  filters: EMPTY_SCM_FILTERS,
  target: { status: 'stockout' as const },
};

beforeEach(() => useScmProducts.mockReset());

describe('ProductListDialog', () => {
  it('renders the enriched metric columns and total count', () => {
    useScmProducts.mockReturnValue(page([prod()], 1));
    render(<ProductListDialog {...baseProps} />);
    const dialog = screen.getByRole('dialog');
    for (const h of ['SKU', 'Status', 'Net position', 'On hand', 'On order', 'Committed', 'Stock valuation']) {
      expect(within(dialog).getByText(h)).toBeInTheDocument();
    }
    expect(within(dialog).getByText(/1 product$/)).toBeInTheDocument();
    // valuation renders (not the em-dash)
    expect(within(dialog).getByText('RM 1,500')).toBeInTheDocument();
  });

  it('renders "—" for a null valuation', () => {
    useScmProducts.mockReturnValue(page([prod({ stock_valuation: null })], 1));
    render(<ProductListDialog {...baseProps} />);
    // Null valuation + null avg-daily-demand + null days-of-cover all render "—".
    expect(within(screen.getByRole('dialog')).getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('exposes the keyboard-accessible net-position formula tooltip', () => {
    useScmProducts.mockReturnValue(page([prod()], 1));
    render(<ProductListDialog {...baseProps} />);
    expect(within(screen.getByRole('dialog')).getByLabelText(NET_POSITION_FORMULA)).toBeInTheDocument();
  });

  it('shows the loading skeleton state', () => {
    useScmProducts.mockReturnValue({ data: undefined, isLoading: true, isFetching: true, isError: false });
    render(<ProductListDialog {...baseProps} />);
    expect(screen.getByText(/Loading products/i)).toBeInTheDocument();
  });

  it('shows the empty state', () => {
    useScmProducts.mockReturnValue(page([], 0));
    render(<ProductListDialog {...baseProps} />);
    expect(screen.getByText(/No products in this scope/i)).toBeInTheDocument();
  });

  it('passes a sort field to the query when a column header is clicked', async () => {
    useScmProducts.mockReturnValue(page([prod()], 1));
    render(<ProductListDialog {...baseProps} />);
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /On hand/i }));
    await waitFor(() => {
      const last = useScmProducts.mock.calls.at(-1);
      expect(last?.[2]).toMatchObject({ sort: 'on_hand', dir: 'asc' });
    });
  });

  it('debounces search into the query', async () => {
    useScmProducts.mockReturnValue(page([prod()], 1));
    render(<ProductListDialog {...baseProps} />);
    fireEvent.change(screen.getByLabelText('Search products'), { target: { value: 'cement' } });
    await waitFor(
      () => {
        const last = useScmProducts.mock.calls.at(-1);
        expect(last?.[2]).toMatchObject({ q: 'cement' });
      },
      { timeout: 1000 },
    );
  });

  it('renders pagination controls when total exceeds one page', () => {
    useScmProducts.mockReturnValue(page([prod()], 120));
    render(<ProductListDialog {...baseProps} />);
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/Page 1 of 3/)).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Previous page')).toBeDisabled();
    expect(within(dialog).getByLabelText('Next page')).toBeEnabled();
  });
});
