/**
 * The order-trend popup: "who bought it" as a table.
 *
 * > "similar to SO - what is the trend of purchase" (user markup, 2026-08-11) names the
 * >  table shape this mirrors on the buy side; the SO side asked for the same thing first:
 * >  Customer | Qty | Last order date, not a bare list of names.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanTrendPopover } from './PlanTrendPopover';
import type { TrajectoryEntry } from '../lib/trajectory';

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

describe('PlanTrendPopover - who bought it', () => {
  it('renders a table with customer, quantity and last order date', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [
            { customer_name: 'Vivo Homes', qty: 120, last_order_date: '2026-07-12' } as never,
            { customer_name: 'Beta Trading', qty: 40, last_order_date: '2026-06-01' } as never,
          ],
        })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('Vivo Homes')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('12/07/2026')).toBeInTheDocument();
    expect(screen.getByText('Beta Trading')).toBeInTheDocument();
    expect(screen.getByText('01/06/2026')).toBeInTheDocument();
  });

  it('says no orders in the window when nobody bought it', () => {
    render(<PlanTrendPopover trend={entry({ customers: [] })} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('No orders in the window.')).toBeInTheDocument();
  });

  it('renders a dash for a customer row with no last-order date on record', () => {
    render(
      <PlanTrendPopover
        trend={entry({
          customers: [{ customer_name: 'Unnamed customer', qty: 5, last_order_date: null } as never],
        })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('-')).toBeInTheDocument();
  });

  it('renders nothing when no trend information exists for the line', () => {
    render(<PlanTrendPopover trend={undefined} />);

    expect(screen.getByText('No order history')).toBeInTheDocument();
  });
});

describe('PlanTrendPopover - selling price (Fix D, user feedback, 2026-08-12)', () => {
  it('renders the selling price above "Who bought it"', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={90} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.getByText('Selling price RM 90.00')).toBeInTheDocument();
  });

  it('omits the line when the selling price is null', () => {
    render(<PlanTrendPopover trend={entry()} sellingPrice={null} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });

  it('omits the line when no selling price prop is passed at all', () => {
    render(<PlanTrendPopover trend={entry()} />);
    fireEvent.click(screen.getByRole('button', { name: /order trend/i }));

    expect(screen.queryByText(/Selling price/)).not.toBeInTheDocument();
  });
});
