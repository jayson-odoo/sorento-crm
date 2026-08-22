/**
 * The suggested-price cell: the number the plan costs the line at, then the verdict on it.
 *
 * > "we need a suggested price to buy ... I need the price & supplier column"
 *
 * Result first, caveat second: the FIGURE is the headline and the verdict ("Ask new
 * price") rides under it. The one thing the cell may never do is imply we know what the
 * item costs today - every claim is about our own ledger.
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

function renderCell(
  price: PriceAdvice | undefined,
  purchasable = true,
  unitCost: number | null = 20.37,
  currency: string | null = 'USD',
) {
  render(
    <PlanPriceCell
      unitCost={unitCost}
      currency={currency}
      price={price}
      staleAfterDays={180}
      purchasable={purchasable}
    />,
  );
}

describe('PlanPriceCell', () => {
  it('leads with the price the plan will buy at, verdict second', () => {
    renderCell(advice());

    expect(screen.getByText('USD 20.37')).toBeInTheDocument();
    expect(screen.getByText('Ask new price')).toBeInTheDocument();
  });

  it('keeps the age behind the number - popup material, not row noise', () => {
    renderCell(advice());

    expect(screen.queryByText(/5 years/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));
    expect(screen.getByText(/5 years/)).toBeInTheDocument();
  });

  it('calls a zero-costed line out and never prints the zero as a price', () => {
    renderCell(advice({ advice: 'zero_cost', standing_cost: 0 }), true, 0);

    expect(screen.getByText('Fix zero price')).toBeInTheDocument();
    expect(screen.queryByText(/USD 0\.00/)).not.toBeInTheDocument();
  });

  it('says never bought in the popup rather than showing a price we do not have', () => {
    renderCell(advice({ advice: 'no_history', last: null, age_days: null }), true, null);

    expect(screen.getByText('Get a quote')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));
    expect(screen.getByText(/no purchase from this supplier/i)).toBeInTheDocument();
  });

  it('renders nothing for an allocation, which has no supplier to have a price with', () => {
    renderCell(advice(), false);

    expect(screen.queryByText('Ask new price')).not.toBeInTheDocument();
    expect(screen.queryByText('USD 20.37')).not.toBeInTheDocument();
  });

  it('still shows the figure with no verdict, but never implies the price is fine', () => {
    renderCell(undefined);

    expect(screen.getByText('USD 20.37')).toBeInTheDocument();
    expect(screen.queryByText('Use last price')).not.toBeInTheDocument();
    expect(screen.getByText(/no purchase history/i)).toBeInTheDocument();
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

describe('the change-supplier suggestion (S13e)', () => {
  const cheaper = {
    supplier_code: 'S-B',
    supplier_name: 'Beta Trading',
    unit_cost: 8,
    currency: 'CNY',
    saving_pct: 20,
  };

  function renderWithCheaper(price: PriceAdvice, c = cheaper) {
    render(
      <PlanPriceCell
        unitCost={20.37}
        currency="USD"
        price={price}
        staleAfterDays={180}
        purchasable
        cheaper={c}
      />,
    );
  }

  it('suggests the switch on a recent price, naming who to ask', () => {
    renderWithCheaper(advice({ advice: 'recent', age_days: 40 }));

    expect(screen.getByText('Ask S-B instead')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));
    expect(screen.getByText(/CNY 8\.00, 20% less/)).toBeInTheDocument();
  });

  it('keeps the price problem as the headline when there is one, and demotes the switch to a note', () => {
    renderWithCheaper(advice()); // stale

    expect(screen.getByText('Ask new price')).toBeInTheDocument();
    expect(screen.queryByText('Ask S-B instead')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /price history/i }));
    expect(screen.getByText(/Beta Trading last charged us CNY 8\.00/)).toBeInTheDocument();
  });

  it('says use last price when nobody on the shortlist is cheaper', () => {
    render(
      <PlanPriceCell
        unitCost={20.37}
        currency="USD"
        price={advice({ advice: 'recent', age_days: 40 })}
        staleAfterDays={180}
        purchasable
        cheaper={null}
      />,
    );

    expect(screen.getByText('Use last price')).toBeInTheDocument();
  });

  it('states its comparable-records basis in the popover, never a market claim', () => {
    renderWithCheaper(advice({ advice: 'recent', age_days: 40 }));

    fireEvent.click(screen.getByRole('button', { name: /price history/i }));
    expect(screen.getByText(/on a comparable basis/)).toBeInTheDocument();
  });
});
