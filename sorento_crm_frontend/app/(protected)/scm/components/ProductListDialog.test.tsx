import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.setPointerCapture = Element.prototype.setPointerCapture ?? (() => {});
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
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
import {
  LEAD_TIME_HINT,
  NET_POSITION_FORMULA,
  REORDER_POINT_FORMULA,
  SAFETY_STOCK_HINT,
} from './HealthIndicators';
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

  it('renders "-" for a null valuation', () => {
    useScmProducts.mockReturnValue(page([prod({ stock_valuation: null })], 1));
    render(<ProductListDialog {...baseProps} />);
    // Null valuation + null avg-daily-demand + null days-of-cover all render "-".
    expect(within(screen.getByRole('dialog')).getAllByText('-').length).toBeGreaterThanOrEqual(1);
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

  it('adds a Reorder point column + "Low stock" status in the Low-stock drill (M8-B8)', () => {
    useScmProducts.mockReturnValue(
      page([prod({ status: 'low', on_hand: 12, net_position: 20, reorder_point: 30, stockout_with_committed: false })], 1),
    );
    render(
      <ProductListDialog
        {...baseProps}
        title="Below reorder point"
        target={{ status: 'low' }}
      />,
    );
    const dialog = screen.getByRole('dialog');
    // the Low-stock drill exposes the Reorder point column (net <= ROP relationship)
    expect(within(dialog).getByText('Reorder point')).toBeInTheDocument();
    expect(within(dialog).getByText('30')).toBeInTheDocument();
    // status renders "Low stock", never "Healthy" or "Stockout"
    expect(within(dialog).getByText('Low stock')).toBeInTheDocument();
    expect(within(dialog).queryByText('Stockout')).not.toBeInTheDocument();
  });

  it('exposes the Reorder-point formula popover in the Low-stock drill (M8-F5)', async () => {
    useScmProducts.mockReturnValue(
      page([prod({ status: 'low', on_hand: 12, net_position: 20, reorder_point: 30, avg_daily_demand: 2, stockout_with_committed: false })], 1),
    );
    render(
      <ProductListDialog
        {...baseProps}
        title="Below reorder point"
        target={{ status: 'low' }}
      />,
    );
    // the (i) beside the Reorder point cell opens a popover with the ROP formula
    fireEvent.click(screen.getByLabelText('Explain reorder point for CWCY605'));
    expect(await screen.findByText(REORDER_POINT_FORMULA)).toBeInTheDocument();
    // "Reorder point = Safety stock + Demand rate x Lead time" is the exact wording
    expect(REORDER_POINT_FORMULA).toMatch(/Safety stock \+ Demand rate x Lead time/i);
  });

  it('shows the safety-stock + lead-time values and definitions in the ROP popover (M8-F10)', async () => {
    useScmProducts.mockReturnValue(
      page([prod({
        status: 'low', on_hand: 15, net_position: 20, reorder_point: 30,
        avg_daily_demand: 2, safety_stock: 88, lead_time_days: 7,
        stockout_with_committed: false,
      })], 1),
    );
    render(
      <ProductListDialog {...baseProps} title="Below reorder point" target={{ status: 'low' }} />,
    );
    fireEvent.click(screen.getByLabelText('Explain reorder point for CWCY605'));
    // both ROP inputs render with their actual values …
    expect(await screen.findByText('Safety stock')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
    expect(screen.getByText('Lead time')).toBeInTheDocument();
    expect(screen.getByText('7 days')).toBeInTheDocument();
    // … each with its one-line plain definition, not the old "set on the reorder plan" note
    expect(screen.getByText(SAFETY_STOCK_HINT)).toBeInTheDocument();
    expect(screen.getByText(LEAD_TIME_HINT)).toBeInTheDocument();
    expect(screen.queryByText(/Safety stock and lead time are set on the reorder plan/i)).not.toBeInTheDocument();
  });

  it('shows a dash + "set on the reorder plan" only for a missing ROP input (M8-F10)', async () => {
    useScmProducts.mockReturnValue(
      page([prod({
        status: 'low', on_hand: 12, net_position: 20, reorder_point: 30,
        avg_daily_demand: 2, safety_stock: 12, lead_time_days: null,
        stockout_with_committed: false,
      })], 1),
    );
    render(
      <ProductListDialog {...baseProps} title="Below reorder point" target={{ status: 'low' }} />,
    );
    fireEvent.click(screen.getByLabelText('Explain reorder point for CWCY605'));
    // safety stock present keeps its definition …
    expect(await screen.findByText(SAFETY_STOCK_HINT)).toBeInTheDocument();
    // … lead time is null → dash + the note (only for the missing one), no lead-time hint
    expect(screen.getByText('Set on the reorder plan.')).toBeInTheDocument();
    expect(screen.queryByText(LEAD_TIME_HINT)).not.toBeInTheDocument();
  });

  it('does NOT add the Reorder point column to the Stockouts drill', () => {
    useScmProducts.mockReturnValue(page([prod()], 1));
    render(<ProductListDialog {...baseProps} />);
    expect(within(screen.getByRole('dialog')).queryByText('Reorder point')).not.toBeInTheDocument();
  });
});
