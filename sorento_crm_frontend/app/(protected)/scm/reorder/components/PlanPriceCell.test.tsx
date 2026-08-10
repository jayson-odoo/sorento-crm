/**
 * The price cell: what we last paid, how old it is, and whether to re-quote.
 *
 * > "should i use the last price, or should i rfq to get new price from supplier"
 *
 * The cell answers that and stops. The one thing it may never do is imply we know what the
 * item costs today.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanPriceCell } from './PlanPriceCell';
import type { PriceAdvice } from '../lib/priceAdvice';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const advice = (over: Partial<PriceAdvice> = {}): PriceAdvice => ({
  advice: 'stale',
  last: { po_number: '202012-S0048', issue_date: '2020-12-15', unit_cost: 20.37, currency: 'USD', qty: 38 },
  previous: null,
  age_days: 2064,
  movement_pct: null,
  currency_changed: false,
  standing_cost: 20.37,
  standing_currency: 'USD',
  standing_gap_pct: 0,
  free_of_charge_lines: 0,
  ...over,
});

function renderCell(price: PriceAdvice | undefined, purchasable = true) {
  render(<PlanPriceCell price={price} staleAfterDays={180} purchasable={purchasable} />);
}

describe('PlanPriceCell', () => {
  it('shows the verdict and the price it is a verdict about', () => {
    renderCell(advice());

    expect(screen.getByText('Re-quote')).toBeInTheDocument();
    expect(screen.getByText(/USD 20\.37/)).toBeInTheDocument();
  });

  it('puts the age on the row, because a price with no date cannot be judged', () => {
    renderCell(advice());

    expect(screen.getByText(/5 years/)).toBeInTheDocument();
  });

  it('calls a zero-costed line out as the loudest thing on the row', () => {
    renderCell(advice({ advice: 'zero_cost', standing_cost: 0 }));

    expect(screen.getByText('Priced at zero')).toBeInTheDocument();
  });

  it('says never bought rather than showing a price we do not have', () => {
    renderCell(advice({ advice: 'no_history', last: null, age_days: null }));

    expect(screen.getByText('Never bought')).toBeInTheDocument();
    expect(screen.getByText(/no purchase on record/i)).toBeInTheDocument();
  });

  it('renders nothing for an allocation, which has no supplier to have a price with', () => {
    renderCell(advice(), false);

    expect(screen.queryByText('Re-quote')).not.toBeInTheDocument();
  });

  it('has no opinion when the facts did not load, rather than implying the price is fine', () => {
    renderCell(undefined);

    expect(screen.queryByText('Price current')).not.toBeInTheDocument();
    expect(screen.queryByText('Re-quote')).not.toBeInTheDocument();
  });

  it('opens the full reasoning, and states the limit of it', () => {
    renderCell(advice());
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));

    expect(screen.getByText(/ask for a fresh quote/i)).toBeInTheDocument();
    expect(screen.getByText(/our own purchase records only/i)).toBeInTheDocument();
  });

  it('shows the purchase before last in the popover so the movement can be checked', () => {
    renderCell(
      advice({
        advice: 'moving',
        age_days: 40,
        movement_pct: 13.2,
        previous: { po_number: 'PO-1', issue_date: '2020-06-01', unit_cost: 18, currency: 'USD', qty: 10 },
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));

    expect(screen.getByText(/USD 18\.00/)).toBeInTheDocument();
    expect(screen.getByText(/\+13\.2%/)).toBeInTheDocument();
  });
});
