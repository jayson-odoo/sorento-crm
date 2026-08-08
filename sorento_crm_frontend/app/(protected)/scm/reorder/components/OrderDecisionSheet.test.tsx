/**
 * OrderDecisionSheet (AC-C2.5 / C2.6 / C2.7 / C2.8 / C3.4 / C3.5).
 *
 * The cases that are the reason the slice exists:
 *
 *  - AC-C2.7: a chosen quantity ABOVE the shortfall is NOT a warning state. 600
 *    against a shortfall of 278 must state what it means (covered, spare and
 *    where it lands, months of cover, cash, volume) with no alert, no
 *    destructive styling and no blocked save.
 *  - The consequence panel NAMES a missing input rather than printing 0. Months
 *    of cover needs a demand statistic and volume needs recorded dimensions, and
 *    most products have neither.
 *  - AC-C2.5: a supplier that has never delivered this item says so, even when
 *    it quotes the lowest cost.
 *  - AC-C2.6: a years-old last PO date is flagged stale.
 *  - AC-C2.8: the engine's suggestion stays visible beside the chosen quantity.
 *
 * The real fixtures from `lib/summaryOrderMockStore` are used rather than
 * hand-typed numbers, so a fixture drifting from the ACs fails here too.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

// jsdom polyfills for Radix Dialog (Sheet).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

const hooks = vi.hoisted(() => ({ useOrderSummarySuppliers: vi.fn() }));
vi.mock('../hooks/useSummaryOrder', () => hooks);

import { SUMMARY_ORDER_FIXTURES } from '../lib/summaryOrderMockStore';
import { OrderDecisionSheet } from './OrderDecisionSheet';
import type { OrderSummaryRow } from '../types/summaryOrder.types';

const OVER_SHORTFALL = SUMMARY_ORDER_FIXTURES.row('B2155-NL-BLUE'); // chosen 600, short 278
const NO_DIMENSIONS = SUMMARY_ORDER_FIXTURES.row('SRTWT7408');
const NEITHER = SUMMARY_ORDER_FIXTURES.row('SRTBS4832');
const STALE_ROW = SUMMARY_ORDER_FIXTURES.row('SRTSK2210');
const NO_SUPPLIER_ROW = SUMMARY_ORDER_FIXTURES.row('SRTAC0904');

const BLUE_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('B2155-NL-BLUE');
const STALE_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('SRTSK2210');

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

const onSave = vi.fn();

function renderSheet(
  hookState: ReturnType<typeof state>,
  row: OrderSummaryRow = OVER_SHORTFALL,
) {
  hooks.useOrderSummarySuppliers.mockReturnValue(hookState);
  render(
    <OrderDecisionSheet
      row={row}
      open
      onOpenChange={() => {}}
      onSave={onSave}
      isSaving={false}
    />,
  );
  return hookState;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('OrderDecisionSheet - states', () => {
  it('renders nothing when no row is being decided', () => {
    hooks.useOrderSummarySuppliers.mockReturnValue(state());
    const { container } = render(
      <OrderDecisionSheet row={null} open onOpenChange={() => {}} onSave={onSave} isSaving={false} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows a skeleton while the supplier candidates load', () => {
    renderSheet(state({ isLoading: true }));
    expect(screen.getByLabelText('Loading supplier candidates')).toBeInTheDocument();
  });

  it('shows the backend message and a retry when the candidates fail to load', () => {
    const s = renderSheet(state({ isError: true, error: new Error('Supplier service down') }));
    expect(screen.getByText('Supplier service down')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Try again/i }));
    expect(s.refetch).toHaveBeenCalled();
  });

  it('states that no supplier is linked rather than leaving the section blank', () => {
    renderSheet(state({ data: SUMMARY_ORDER_FIXTURES.suppliers('SRTAC0904') }), NO_SUPPLIER_ROW);
    expect(screen.getByText('No supplier linked to this item')).toBeInTheDocument();
  });

  it('renders the position the decision is taken against', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const position = screen.getByRole('region', { name: 'Position' });
    expect(position).toHaveTextContent('On hand');
    expect(position).toHaveTextContent('96');
    expect(position).toHaveTextContent('278');
  });
});

describe('OrderDecisionSheet - a quantity above the shortfall is not a warning (AC-C2.7)', () => {
  it('states what the chosen 600 does against a shortfall of 278, in plain figures', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const headline = screen.getByTestId('impact-headline');
    expect(headline).toHaveTextContent('Covers 278 of the 278 short');
    expect(headline).toHaveTextContent('creates 322 spare in BRW');
  });

  it('never renders the excess as an alert or in destructive tone', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    const consequence = screen.getByRole('region', { name: 'What this order does' });
    expect(consequence.querySelector('.text-destructive')).toBeNull();
    expect(consequence.querySelector('.text-scm-stockout')).toBeNull();
    expect(consequence.textContent).not.toMatch(/warning|too much|exceeds/i);
  });

  it('keeps the save enabled for a quantity above the shortfall', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const save = screen.getByRole('button', { name: 'Record decision' });
    expect(save).not.toBeDisabled();
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledWith({ chosen_qty: 600, supplier_code: 'GDS' });
  });

  it('states the remaining shortfall when the quantity is BELOW it, still without an alert', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    fireEvent.change(screen.getByLabelText(/Order quantity/i), { target: { value: '100' } });
    expect(screen.getByTestId('impact-headline')).toHaveTextContent(
      'leaving 178 still short',
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('states cover, cash and volume for a product that has all three inputs', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    // 96 + 120 + 200 + 600 - 480 - 186 = 350, over 3.6/day -> 3.2 months.
    expect(screen.getByTestId('impact-cover')).toHaveTextContent('3.2 months');
    expect(screen.getByTestId('impact-cash')).toHaveTextContent('CNY 77,040.00');
    expect(screen.getByTestId('impact-volume')).toHaveTextContent('49.2 m3');
  });

  it('recomputes the consequence as the quantity is typed', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    fireEvent.change(screen.getByLabelText(/Order quantity/i), { target: { value: '300' } });
    expect(screen.getByTestId('impact-cash')).toHaveTextContent('CNY 38,520.00');
    expect(screen.getByTestId('impact-headline')).toHaveTextContent('creates 22 spare in BRW');
  });
});

describe('OrderDecisionSheet - a missing input is named, never zeroed', () => {
  it('says dimensions are not recorded instead of a volume of 0', () => {
    renderSheet(state({ data: SUMMARY_ORDER_FIXTURES.suppliers('SRTWT7408') }), NO_DIMENSIONS);
    expect(screen.getByTestId('impact-volume')).toHaveTextContent('dimensions not recorded');
    expect(screen.getByTestId('impact-volume')).not.toHaveTextContent('0.0 m3');
  });

  it('says the demand rate is not recorded instead of a cover of 0 months', () => {
    renderSheet(state({ data: SUMMARY_ORDER_FIXTURES.suppliers('SRTBS4832') }), NEITHER);
    expect(screen.getByTestId('impact-cover')).toHaveTextContent('demand rate not recorded');
    expect(screen.getByTestId('impact-cover')).not.toHaveTextContent('0.0 months');
    expect(screen.getByTestId('impact-volume')).toHaveTextContent('dimensions not recorded');
  });

  it('says no supplier is chosen yet instead of committing cash at an assumed cost', () => {
    renderSheet(state({ data: SUMMARY_ORDER_FIXTURES.suppliers('SRTBS4832') }), NEITHER);
    expect(screen.getByTestId('impact-cash')).toHaveTextContent('no supplier chosen yet');
  });
});

describe('OrderDecisionSheet - the engine keeps its own figure (AC-C2.8)', () => {
  it('shows the suggested quantity beside the chosen one', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    expect(screen.getByTestId('suggested-qty')).toHaveTextContent('300');
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('600');
  });

  it('names who last set the quantity and when, so a larger number is on the record', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    expect(screen.getByText(/Last set to 600 by Loo Keng Hoe/)).toBeInTheDocument();
  });

  it('opens an undecided row at the engine suggestion rather than at zero', () => {
    renderSheet(state({ data: STALE_SUPPLIERS }), STALE_ROW);
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('50');
  });

  it('resets to the suggestion on demand without overwriting it', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    fireEvent.click(screen.getByRole('button', { name: 'Use suggestion' }));
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('300');
    expect(screen.getByTestId('suggested-qty')).toHaveTextContent('300');
  });
});

describe('OrderDecisionSheet - supplier is a choice, not a fixed value (AC-C2.5 / C3.5)', () => {
  it('shows cost, last PO date, incoming cost, variance, on-time rate and lead time', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const gds = screen.getByTestId('supplier-GDS');
    expect(gds).toHaveTextContent('CNY 128.40');
    expect(gds).toHaveTextContent('12/06/2026');
    expect(gds).toHaveTextContent('CNY 134.90');
    expect(gds).toHaveTextContent('+CNY 6.50');
    expect(gds).toHaveTextContent('86%');
    expect(gds).toHaveTextContent('52 days');
  });

  it('labels both costs ex-works, never as a landed cost (AC-C3.4)', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const gds = screen.getByTestId('supplier-GDS');
    expect(within(gds).getByText('Last PO cost (ex-works)')).toBeInTheDocument();
    expect(within(gds).getByText('Incoming cost (ex-works)')).toBeInTheDocument();
    expect(gds.textContent).not.toMatch(/landed/i);
  });

  it('says a candidate has never delivered this item, even when it is the cheapest', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const zqh = screen.getByTestId('supplier-ZQH');
    // Lowest cost on the list.
    expect(zqh).toHaveTextContent('CNY 112.75');
    expect(within(zqh).getByText('never delivered this item')).toBeInTheDocument();
    expect(zqh).toHaveTextContent('never received');
  });

  it('lets the buyer switch supplier, which re-states the cash committed', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    fireEvent.click(screen.getByTestId('supplier-ZQH'));
    expect(screen.getByTestId('supplier-ZQH')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('impact-cash')).toHaveTextContent('CNY 67,650.00');
    fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
    expect(onSave).toHaveBeenCalledWith({ chosen_qty: 600, supplier_code: 'ZQH' });
  });

  it('cannot be saved with no supplier picked', () => {
    renderSheet(state({ data: SUMMARY_ORDER_FIXTURES.suppliers('SRTSK2210') }), STALE_ROW);
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  });
});

describe('OrderDecisionSheet - a stale last PO date is flagged (AC-C2.6)', () => {
  it('flags the 2021 purchase as stale and says how long ago it was', () => {
    renderSheet(state({ data: STALE_SUPPLIERS }), STALE_ROW);
    const ipm = screen.getByTestId('supplier-IPM');
    expect(within(ipm).getByText('stale')).toBeInTheDocument();
    expect(screen.getByTestId('last-po-date-IPM')).toHaveTextContent('18/11/2021');
    expect(screen.getByTestId('last-po-date-IPM')).toHaveTextContent('1,719 days ago');
  });

  it('does NOT flag a supplier bought from this year', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    const gds = screen.getByTestId('supplier-GDS');
    expect(within(gds).queryByText('stale')).not.toBeInTheDocument();
  });
});
