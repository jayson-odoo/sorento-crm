/**
 * The order-trend popup: "who bought it" as a table, and the orders behind each name.
 *
 * > "similar to SO - what is the trend of purchase" (user markup, 2026-08-11) names the
 * >  table shape this mirrors on the buy side; the SO side asked for the same thing first:
 * >  Customer | Qty | Last order date, not a bare list of names. A quantity beside a name
 * >  still does not answer "sells RM 0.94?", which is what the expand is for.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import type { TrajectoryEntry } from '../lib/trajectory';

const useCustomerOrders = vi.fn();
vi.mock('../hooks/useReorderRun', () => ({
  useCustomerOrders: (...a: unknown[]) => useCustomerOrders(...a),
}));

import { PlanTrendPopover } from './PlanTrendPopover';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

vi.mock('react-apexcharts', () => ({
  default: () => <div data-testid="trend-chart" />,
}));

const entry = (over: Partial<TrajectoryEntry> = {}): TrajectoryEntry => ({
  verdict: 'rising',
  recent_qty: 120,
  previous_qty: 90,
  change_pct: 33.33,
  year_ago_qty: 200,
  year_change_pct: -40,
  window_months: 12,
  months: [],
  customers: [],
  agents: [],
  agents_available: false,
  ...over,
});

const orders = (over: Record<string, unknown> = {}) => ({
  lines: [
    { so_number: 'SO414050', order_date: '2026-07-12', qty: 60, unit_price: 0.94, warehouse_code: 'BRW-BB' },
    { so_number: 'SO414051', order_date: '2026-06-05', qty: 40, unit_price: null, warehouse_code: 'BRW-BB' },
  ],
  total: 2,
  shown: 2,
  ...over,
});

function stubOrders(data: unknown, extra: Record<string, unknown> = {}) {
  useCustomerOrders.mockReturnValue({
    data, isLoading: false, isError: false, error: null, ...extra,
  });
}

beforeEach(() => {
  useCustomerOrders.mockReset();
  stubOrders(orders());
});

const customer = (over: Record<string, unknown> = {}) => ({
  customer_name: 'Vivo Homes',
  customer_key: 'cust-1',
  qty: 120,
  last_order_date: '2026-07-12',
  ...over,
});

function openTrend() {
  fireEvent.click(screen.getByRole('button', { name: /order trend/i }));
}

describe('PlanTrendPopover - who bought it', () => {
  it('renders a table with customer, quantity and last order date', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [
            customer() as never,
            customer({ customer_name: 'Beta Trading', customer_key: 'cust-2', qty: 40, last_order_date: '2026-06-01' }) as never,
          ],
        })}
      />,
    );
    openTrend();

    expect(screen.getByText('Vivo Homes')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('12/07/2026')).toBeInTheDocument();
    expect(screen.getByText('Beta Trading')).toBeInTheDocument();
    expect(screen.getByText('01/06/2026')).toBeInTheDocument();
  });

  it('says no orders in the window when nobody bought it', () => {
    render(<PlanTrendPopover trend={entry({ customers: [] })} />);
    openTrend();

    expect(screen.getByText('No orders in the window.')).toBeInTheDocument();
  });

  it('renders a dash for a customer row with no last-order date on record', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [customer({ customer_name: 'No customer on order', customer_key: 'none', qty: 5, last_order_date: null }) as never],
        })}
      />,
    );
    openTrend();

    expect(screen.getByText('-')).toBeInTheDocument();
  });
});

describe('PlanTrendPopover - the orders behind a customer (AC-4.1)', () => {
  const rendered = () =>
    render(
      <PlanTrendPopover
        trend={entry({ customers: [customer() as never] })}
        runId="run-1"
        productId="prod-1"
        segment="project"
      />,
    );

  it('does not fetch until the row is expanded', () => {
    // The query lives inside the expanded row, so a popover listing five customers holds
    // no subscription for the four nobody opened.
    rendered();
    openTrend();

    expect(useCustomerOrders).not.toHaveBeenCalled();
  });

  it('fetches and renders SO, date, qty and price when expanded', async () => {
    rendered();
    openTrend();
    fireEvent.click(screen.getByRole('button', { name: /Vivo Homes/ }));

    await waitFor(() =>
      expect(useCustomerOrders).toHaveBeenCalledWith('run-1', 'prod-1', 'project', 'cust-1', true),
    );
    expect(screen.getByText('SO414050')).toBeInTheDocument();
    expect(screen.getByText('60')).toBeInTheDocument();
    expect(screen.getByText('RM 0.94')).toBeInTheDocument();
    // Twice: the customer row's "last order" IS this order's date.
    expect(screen.getAllByText('12/07/2026')).toHaveLength(2);
  });

  it('marks the row expanded so the disclosure is announced', () => {
    rendered();
    openTrend();
    const row = screen.getByRole('button', { name: /Vivo Homes/ });

    expect(row).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
  });

  it('says how many orders it is NOT showing rather than dropping them silently', () => {
    stubOrders(orders({ total: 27, shown: 2 }));
    rendered();
    openTrend();
    fireEvent.click(screen.getByRole('button', { name: /Vivo Homes/ }));

    expect(screen.getByText('25 more')).toBeInTheDocument();
  });

  it('shows a loading state while the orders are being fetched', () => {
    stubOrders(undefined, { isLoading: true });
    rendered();
    openTrend();
    fireEvent.click(screen.getByRole('button', { name: /Vivo Homes/ }));

    expect(screen.queryByText('SO414050')).not.toBeInTheDocument();
  });

  it('surfaces the error rather than an empty list', () => {
    stubOrders(undefined, { isError: true, error: new Error('Backend said no') });
    rendered();
    openTrend();
    fireEvent.click(screen.getByRole('button', { name: /Vivo Homes/ }));

    expect(screen.getByText('Backend said no')).toBeInTheDocument();
  });
});

describe('PlanTrendPopover - a line with open demand and no dated history (AC-4.4)', () => {
  it('says the window is empty, not that the product has no history', () => {
    render(<PlanTrendPopover trend={undefined} />);

    expect(screen.getByText('No orders dated in the last 24 months.')).toBeInTheDocument();
    expect(screen.queryByText(/Open now/)).not.toBeInTheDocument();
  });

  it('says what is open now when the row carries open demand', () => {
    // The outstanding book never wrote an order date, so a row really can carry 51 open
    // units and no dated history at all. "No order history" beside them read as a defect.
    render(<PlanTrendPopover trend={undefined} outstandingSales={51} />);

    expect(screen.getByText('No orders dated in the last 24 months.')).toBeInTheDocument();
    expect(screen.getByText('Open now: 51 (see Demand)')).toBeInTheDocument();
  });
});

describe('PlanTrendPopover - selling price (Fix D, user feedback, 2026-08-12)', () => {
  it('renders the selling price above "Who bought it"', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={90} />);
    openTrend();

    expect(screen.getByText('Selling price RM 90.00')).toBeInTheDocument();
  });

  it('omits the line when the selling price is null', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={null} />);
    openTrend();

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });

  it('omits the line when no selling price prop is passed at all', () => {
    render(<PlanTrendPopover trend={entry()} />);
    openTrend();

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });
});
