/**
 * The health popover's margin arithmetic.
 *
 * > "Current health popover says 'Margin 33.3% vs list price' with no numbers." The popup
 * >  must show the three figures the badge is computed from - never a bare percentage, and
 * >  never a fabricated one when the selling price is not on file.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanHealthCell } from './PlanHealthCell';
import { marginOf, type ProductEconomics } from '../lib/productHealth';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
  product_id: 'p1',
  avg_sell_price: 90,
  sell_source: 'orders',
  sold_qty: 240,
  on_hand: 40,
  avg_monthly_out: 20,
  turnover_months: 2,
  no_movement: false,
  lifecycle_decision: null,
  lifecycle_decided_at: null,
  ...over,
});

function open() {
  fireEvent.click(screen.getByRole('button', { name: /product health/i }));
}

describe('PlanHealthCell - margin arithmetic', () => {
  it('renders the selling price, cost and margin figures, with the percentage', () => {
    render(
      <PlanHealthCell margin={marginOf(60, econ(), 15)} advice={null} econ={econ()} />,
    );
    open();

    expect(screen.getByText('Selling price')).toBeInTheDocument();
    expect(screen.getByText('RM 90.00')).toBeInTheDocument();
    expect(screen.getByText('Cost')).toBeInTheDocument();
    expect(screen.getByText('RM 60.00')).toBeInTheDocument();
    expect(screen.getByText('Margin')).toBeInTheDocument();
    expect(screen.getByText('RM 30.00 (33.3%)')).toBeInTheDocument();
  });

  it('never fabricates a percentage when the selling price is not set', () => {
    const noSell = econ({ avg_sell_price: null, sell_source: null });
    render(<PlanHealthCell margin={marginOf(60, noSell, 15)} advice={null} econ={noSell} />);
    open();

    expect(screen.getByText('Selling price not set - margin unknown.')).toBeInTheDocument();
    expect(screen.queryByText(/%\)/)).not.toBeInTheDocument();
  });

  it('names the cost as the missing side when the cost is not set', () => {
    render(<PlanHealthCell margin={marginOf(null, econ(), 15)} advice={null} econ={econ()} />);
    open();

    expect(screen.getByText('Cost not set - margin unknown.')).toBeInTheDocument();
  });

  it('treats a zero cost as unset rather than a 100% margin', () => {
    render(<PlanHealthCell margin={marginOf(0, econ(), 15)} advice={null} econ={econ()} />);
    open();

    expect(screen.getByText('Cost not set - margin unknown.')).toBeInTheDocument();
  });

  it('renders nothing at all when there is no economics opinion for the product', () => {
    render(<PlanHealthCell margin={null} advice={null} econ={null} />);

    expect(screen.queryByRole('button', { name: /product health/i })).not.toBeInTheDocument();
  });
});

describe('PlanHealthCell - pill content (Fix C, user feedback, 2026-08-12)', () => {
  it('shows the margin amount alongside the percentage, no subtitle', () => {
    // unit_cost 60 vs sells 90 -> 33.3%, RM 30.00.
    render(<PlanHealthCell margin={marginOf(60, econ(), 15)} advice={null} econ={econ()} />);

    expect(screen.getByText('Margin 33.3% (RM 30.00)')).toBeInTheDocument();
    expect(screen.queryByText(/vs list price/i)).not.toBeInTheDocument();
  });

  it('drops the "vs list price - nothing sold" subtitle for a list-price-only margin', () => {
    const noSales = econ({ avg_sell_price: 90, sell_source: 'list_price', sold_qty: 0 });
    render(<PlanHealthCell margin={marginOf(60, noSales, 15)} advice={null} econ={noSales} />);

    expect(screen.getByText('Margin 33.3% (RM 30.00)')).toBeInTheDocument();
    expect(screen.queryByText('vs list price - nothing sold')).not.toBeInTheDocument();
    // The nuance still lives in the popover body, just not on the pill.
    open();
    expect(
      screen.getByText('No sales in the window, so the margin compares against the list price.'),
    ).toBeInTheDocument();
  });

  it('keeps "Margin unknown" (no amount) when the margin cannot be computed', () => {
    const noSell = econ({ avg_sell_price: null, sell_source: null });
    render(<PlanHealthCell margin={marginOf(60, noSell, 15)} advice={null} econ={noSell} />);

    expect(screen.getByText('Margin unknown')).toBeInTheDocument();
    expect(screen.queryByText(/RM/)).not.toBeInTheDocument();
  });
});
