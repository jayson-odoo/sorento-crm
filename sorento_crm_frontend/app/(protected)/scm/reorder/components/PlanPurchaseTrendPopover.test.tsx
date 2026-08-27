/**
 * The PO cell's mirror of the order-trend popup.
 *
 * > "similar to SO - what is the trend of purchase, then the list of supplier, purchase
 * >  date, purchase quantity, purchase cost" (user markup, 2026-08-11)
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanPurchaseTrendPopover } from './PlanPurchaseTrendPopover';
import type { ProductPurchaseTrend } from '../lib/purchaseTrend';
import type { PriceAdvice } from '../lib/priceAdvice';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const trend = (over: Partial<ProductPurchaseTrend> = {}): ProductPurchaseTrend => ({
  recent_qty: 400,
  previous_qty: 1200,
  lines: [
    {
      supplier_code: 'S-1', supplier_name: 'Acme Supplies', po_number: 'PO-1',
      order_date: '2026-07-01', qty: 100, unit_cost: 72, currency: 'USD',
    },
  ],
  ...over,
});

const advice = (over: Partial<PriceAdvice> = {}): PriceAdvice => ({
  advice: 'moving',
  last: { po_number: 'PO-1', issue_date: '2026-07-01', unit_cost: 72, currency: 'USD', qty: 100 },
  previous: { po_number: 'PO-0', issue_date: '2026-03-01', unit_cost: 60, currency: 'USD', qty: 200 },
  age_days: 40,
  movement_pct: 20,
  currency_changed: false,
  standing_cost: 72,
  standing_currency: 'USD',
  standing_gap_pct: 0,
  free_of_charge_lines: 0,
  ...over,
});

function open() {
  fireEvent.click(screen.getByRole('button', { name: /purchase trend/i }));
}

describe('PlanPurchaseTrendPopover', () => {
  it('shows the PO figure as the trigger and the trend sentence in the popup', () => {
    render(<PlanPurchaseTrendPopover qty={210} trend={trend()} windowMonths={3} />);

    expect(screen.getByText('210')).toBeInTheDocument();
    open();
    expect(
      screen.getByText('Ordered 400 in the last 3 months, 1,200 in the 3 months before.'),
    ).toBeInTheDocument();
  });

  it('renders the purchase lines as a Supplier/Date/Qty/Unit cost table', () => {
    render(<PlanPurchaseTrendPopover qty={210} trend={trend()} windowMonths={3} />);
    open();

    expect(screen.getByText('Acme Supplies')).toBeInTheDocument();
    expect(screen.getByText('01/07/2026')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('USD 72.00')).toBeInTheDocument();
  });

  it('says never purchased when there is no history for this product', () => {
    render(
      <PlanPurchaseTrendPopover
        qty={0}
        trend={{ recent_qty: 0, previous_qty: 0, lines: [] }}
        windowMonths={3}
      />,
    );
    open();

    expect(screen.getByText('Never ordered in the imported history.')).toBeInTheDocument();
    expect(screen.getByText('No purchases in the imported history.')).toBeInTheDocument();
  });

  it('shows the last-vs-previous comparison with a positive sign when the price rose', () => {
    render(
      <PlanPurchaseTrendPopover qty={210} trend={trend()} windowMonths={3} price={advice()} />,
    );
    open();

    expect(screen.getByText(/Last USD 72\.00 vs previous USD 60\.00 \(\+20\.0%\)/)).toBeInTheDocument();
  });

  it('shows a negative sign when the price fell', () => {
    render(
      <PlanPurchaseTrendPopover
        qty={210}
        trend={trend()}
        windowMonths={3}
        price={advice({ movement_pct: -15 })}
      />,
    );
    open();

    expect(screen.getByText(/\(-15\.0%\)/)).toBeInTheDocument();
  });

  it('omits the comparison line when there is no previous purchase to compare against', () => {
    render(
      <PlanPurchaseTrendPopover
        qty={210}
        trend={trend()}
        windowMonths={3}
        price={advice({ previous: null, movement_pct: null })}
      />,
    );
    open();

    expect(screen.queryByText(/vs previous/)).not.toBeInTheDocument();
  });

  it('renders a dash trigger for a null/undefined PO quantity', () => {
    render(<PlanPurchaseTrendPopover qty={null} trend={undefined} windowMonths={3} />);

    expect(screen.getByText('-')).toBeInTheDocument();
  });

  describe('lazy fetch trigger (Fix 5, 2026-08-12: no eager purchase-trend fetch on plan mount)', () => {
    it('fires onOpen the first time the popover opens', () => {
      const onOpen = vi.fn();
      render(<PlanPurchaseTrendPopover qty={210} trend={trend()} windowMonths={3} onOpen={onOpen} />);

      expect(onOpen).not.toHaveBeenCalled();
      open();
      expect(onOpen).toHaveBeenCalledTimes(1);
    });

    it('never calls onOpen just from rendering the trigger unopened', () => {
      const onOpen = vi.fn();
      render(<PlanPurchaseTrendPopover qty={210} trend={undefined} windowMonths={3} onOpen={onOpen} />);
      expect(onOpen).not.toHaveBeenCalled();
    });

    it('tolerates no onOpen callback at all', () => {
      expect(() => {
        render(<PlanPurchaseTrendPopover qty={210} trend={trend()} windowMonths={3} />);
        open();
      }).not.toThrow();
    });
  });
});
