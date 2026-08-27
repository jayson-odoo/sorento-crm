/**
 * The shortlist inside "Why this supplier" is a price comparison, so every price on it
 * has to say what money it is in.
 *
 * The book is mostly USD against a ringgit base. Printed bare, a USD 8.00 alternative sits
 * under an RM 10.00 chosen supplier and reads as the cheaper option while actually costing
 * about three times more - a wrong conclusion drawn from a correctly-fetched number.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { PlanSupplierCell } from './PlanSupplierCell';
import type { PlanRowSupplier, PlanRowSupplierOption } from '../lib/planRow';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);

const chosen: PlanRowSupplier = {
  code: 'SUP-ACME',
  name: 'Acme Sanitary',
  unit_cost: 10,
  lead_time_days: 14,
};

const option = (over: Partial<PlanRowSupplierOption> = {}): PlanRowSupplierOption => ({
  value: 'SUP-BETA',
  label: 'Beta Supplies',
  unit_cost: 8,
  currency: 'USD',
  unit_cost_base: 36,
  lead_time_days: 21,
  ...over,
});

function renderCell(alternatives: PlanRowSupplierOption[]) {
  render(
    <PlanSupplierCell
      supplier={chosen}
      alternatives={alternatives}
      price={undefined}
      cheaper={null}
      purchasable
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /why this supplier/i }));
}

describe('PlanSupplierCell - the shortlist prices', () => {
  it('names the currency of a foreign alternative rather than printing a bare number', () => {
    renderCell([option()]);

    expect(screen.getByText(/USD 8\.00/)).toBeInTheDocument();
    expect(screen.queryByText(/^8\.00/)).not.toBeInTheDocument();
  });

  it('reads an alternative with no currency on file as the base currency', () => {
    renderCell([option({ currency: null, unit_cost: 9.5, unit_cost_base: 9.5 })]);

    expect(screen.getByText(/RM 9\.50/)).toBeInTheDocument();
  });

  it('keeps the lead time beside the price', () => {
    renderCell([option()]);

    expect(screen.getByText(/USD 8\.00 \(RM 36\.00\), 21d/)).toBeInTheDocument();
  });

  it('does not restate a base-currency price as itself', () => {
    renderCell([option({ currency: 'MYR', unit_cost: 9.5, unit_cost_base: 9.5 })]);

    expect(screen.getByText(/RM 9\.50, 21d/)).toBeInTheDocument();
    expect(screen.queryByText(/RM 9\.50 \(RM 9\.50\)/)).not.toBeInTheDocument();
  });

  it('shows only the quoted price when the currency has no rate to restate it with', () => {
    renderCell([option({ unit_cost_base: null })]);

    expect(screen.getByText(/USD 8\.00, 21d/)).toBeInTheDocument();
  });

  it('shows the restated price when the alternative is in another currency', () => {
    // The ranking happened in ringgit, so the comparable figure travels with the raw one -
    // otherwise the reader has to do an exchange-rate sum to know which is cheaper.
    renderCell([option()]);

    expect(screen.getByText(/RM 36\.00/)).toBeInTheDocument();
  });

  it('renders no shortlist section when this is the only supplier', () => {
    renderCell([]);

    expect(screen.getByText('The only supplier linked to this product.')).toBeInTheDocument();
    expect(screen.queryByText('Also on the shortlist')).not.toBeInTheDocument();
  });
});


describe('PlanSupplierCell - the supplier select (AC-R14)', () => {
  const options = [
    { value: 'SUP-ACME', label: 'Acme Sanitary', unit_cost: 10, currency: 'MYR',
      unit_cost_base: 10, lead_time_days: 14 },
    option(),
  ];

  it('offers the product\u2019s own suppliers, the engine\u2019s proposal first', async () => {
    render(
      <PlanSupplierCell
        supplier={chosen}
        alternatives={options}
        price={undefined}
        cheaper={null}
        purchasable
        chosenCode="SUP-ACME"
        onSupplierChange={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('combobox'));
    expect(await screen.findByRole('option', { name: /Acme Sanitary/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Beta Supplies/ })).toBeInTheDocument();
  });

  it('picking the other supplier records its CODE, never an id', async () => {
    const onSupplierChange = vi.fn();
    render(
      <PlanSupplierCell
        supplier={chosen}
        alternatives={options}
        price={undefined}
        cheaper={null}
        purchasable
        chosenCode="SUP-ACME"
        onSupplierChange={onSupplierChange}
      />,
    );

    fireEvent.click(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', { name: /Beta Supplies/ }));
    expect(onSupplierChange).toHaveBeenCalledWith('SUP-BETA');
  });

  it('the row reads the chosen supplier\u2019s own lead time, not the engine\u2019s', () => {
    render(
      <PlanSupplierCell
        supplier={chosen}
        alternatives={options}
        price={undefined}
        cheaper={null}
        purchasable
        chosenCode="SUP-BETA"
        onSupplierChange={vi.fn()}
      />,
    );

    expect(screen.getByText('SUP-BETA, 21 day lead')).toBeInTheDocument();
    expect(screen.queryByText('SUP-ACME, 14 day lead')).not.toBeInTheDocument();
  });

  it('offers no select when the product has only one supplier', () => {
    render(
      <PlanSupplierCell
        supplier={chosen}
        alternatives={[options[0]]}
        price={undefined}
        cheaper={null}
        purchasable
        onSupplierChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });
});
