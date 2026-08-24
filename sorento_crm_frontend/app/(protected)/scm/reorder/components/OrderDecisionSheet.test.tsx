/**
 * OrderDecisionSheet (AC-C2.5 / C2.6 / C2.7 / C2.8 / C3.4 / C3.5).
 *
 * The cases that are the reason the slice exists:
 *
 * - AC-C2.7: a chosen quantity ABOVE the shortfall is NOT a warning state. 600
 *    against a shortfall of 278 must state what it means (covered, spare and
 *    where it lands, months of cover, cash, volume) with no alert, no
 *    destructive styling and no blocked save.
 * - The consequence panel NAMES a missing input rather than printing 0. Months
 *    of cover needs a demand statistic and volume needs recorded dimensions, and
 *    most products have neither.
 * - AC-C2.5: a supplier that has never delivered this item says so, even when
 *    it quotes the lowest cost.
 * - AC-C2.6: a years-old last PO date is flagged stale.
 * - AC-C2.8: the engine's suggestion stays visible beside the chosen quantity.
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
import type { OrderSummaryDecisionResult, OrderSummaryRow } from '../types/summaryOrder.types';

const OVER_SHORTFALL = SUMMARY_ORDER_FIXTURES.row('B2155-NL-BLUE'); // chosen 600, short 278
const NO_DIMENSIONS = SUMMARY_ORDER_FIXTURES.row('SRTWT7408');
const NEITHER = SUMMARY_ORDER_FIXTURES.row('SRTBS4832');
const STALE_ROW = SUMMARY_ORDER_FIXTURES.row('SRTSK2210');
const NO_SUPPLIER_ROW = SUMMARY_ORDER_FIXTURES.row('SRTAC0904');
// AC-F12 pair: EA at 0 decimal places refuses 2.5; kg at 3 accepts it.
const DP0_ROW = SUMMARY_ORDER_FIXTURES.row('SRTTB1120');
const DP3_ROW = SUMMARY_ORDER_FIXTURES.row('SRTAD9002');

const BLUE_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('B2155-NL-BLUE');
const STALE_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('SRTSK2210');
const DP0_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('SRTTB1120');
const DP3_SUPPLIERS = SUMMARY_ORDER_FIXTURES.suppliers('SRTAD9002');

function state(over: Record<string, unknown> = {}) {
  return { data: undefined, isLoading: false, isError: false, error: null, refetch: vi.fn(), ...over };
}

const onSave = vi.fn();

function renderSheet(
  hookState: ReturnType<typeof state>,
  row: OrderSummaryRow = OVER_SHORTFALL,
  over: Partial<React.ComponentProps<typeof OrderDecisionSheet>> = {},
) {
  hooks.useOrderSummarySuppliers.mockReturnValue(hookState);
  render(
    <OrderDecisionSheet
      row={row}
      open
      onOpenChange={() => {}}
      onSave={onSave}
      isSaving={false}
      {...over}
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

describe('OrderDecisionSheet - the incoming cost is labelled with the SHIPMENT currency', () => {
  function withIncoming(currency: string | null) {
    const base = SUMMARY_ORDER_FIXTURES.suppliers('B2155-NL-BLUE');
    return {
      ...base,
      candidates: base.candidates.map((c) =>
        c.supplier_code === 'GDS'
          ? { ...c, currency: 'MYR', last_incoming_cost: 250, last_incoming_currency: currency }
          : c,
      ),
    };
  }

  it('uses the shipment line currency, not the purchase order one', () => {
    // The packing-list ingest stores the supplier's own money (CNY) while the order sits in
    // MYR, so borrowing the PO's code printed "RM 250.00" for a price of CNY 250.00.
    renderSheet(state({ data: withIncoming('CNY') }));
    const gds = screen.getByTestId('supplier-GDS');
    expect(gds).toHaveTextContent('CNY 250.00');
    expect(gds).not.toHaveTextContent('RM 250.00');
  });

  it('shows the figure unlabelled when the shipment states no currency', () => {
    renderSheet(state({ data: withIncoming(null) }));
    const gds = screen.getByTestId('supplier-GDS');
    expect(gds).toHaveTextContent('250.00');
    expect(gds).not.toHaveTextContent('RM 250.00');
    expect(gds).not.toHaveTextContent('CNY 250.00');
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

describe('OrderDecisionSheet - the quantity obeys the row FROZEN uom_decimal_places (AC-F12)', () => {
  it('a whole-unit (dp 0) field strips the decimal point as it is typed, so 2.5 lands as 25', () => {
    // `sanitizeQtyInput` is the first line of defence: at dp 0 the separator can never
    // even be typed, so a fractional quantity cannot be entered by accident.
    renderSheet(state({ data: DP0_SUPPLIERS }), DP0_ROW);
    fireEvent.change(screen.getByLabelText(/Order quantity/i), { target: { value: '2.5' } });
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('25');
    expect(screen.getByTestId('precision-hint')).toHaveTextContent('Whole units only (EA)');
  });

  it('refuses an already-invalid precision it did not sanitize itself, and disables save', () => {
    // The second line of defence: a row that ARRIVES with a value finer than its own
    // frozen precision (e.g. `chosen_qty` set before the row's dp was known) is still
    // caught, because the initial fill in `useEffect` reads `row.chosen_qty` directly
    // and does not run it through `sanitizeQtyInput`.
    const badRow: OrderSummaryRow = { ...DP0_ROW, chosen_qty: 2.5 };
    renderSheet(state({ data: DP0_SUPPLIERS }), badRow);
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('2.5');
    expect(screen.getByTestId('precision-error')).toHaveTextContent(
      'Whole units only for EA. Remove the decimals.',
    );
    fireEvent.click(screen.getByTestId('supplier-ZQH'));
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  });

  it('a measure unit at dp 3 accepts 2.75 as typed, with no digits stripped', () => {
    renderSheet(state({ data: DP3_SUPPLIERS }), DP3_ROW);
    fireEvent.change(screen.getByLabelText(/Order quantity/i), { target: { value: '2.75' } });
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('2.75');
    expect(screen.queryByTestId('precision-error')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('supplier-IPM'));
    expect(screen.getByRole('button', { name: 'Record decision' })).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Record decision' }));
    expect(onSave).toHaveBeenCalledWith({ chosen_qty: 2.75, supplier_code: 'IPM' });
  });

  it('caps typing at dp 3 rather than letting a 4th fractional digit through', () => {
    renderSheet(state({ data: DP3_SUPPLIERS }), DP3_ROW);
    fireEvent.change(screen.getByLabelText(/Order quantity/i), { target: { value: '2.7555' } });
    expect(screen.getByLabelText(/Order quantity/i)).toHaveValue('2.755');
    expect(screen.getByTestId('precision-hint')).toHaveTextContent('Up to 3 decimal places (kg)');
  });
});

describe('OrderDecisionSheet - decision-lock-reason (AC-F09 / AC-F10)', () => {
  it('renders the lock reason and disables save on a run decided at the other grain', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }), OVER_SHORTFALL, {
      lockReason: 'Decided at Location grain',
    });
    expect(screen.getByTestId('decision-lock-reason')).toHaveTextContent(
      'Decided at Location grain',
    );
    fireEvent.click(screen.getByTestId('supplier-GDS'));
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  });

  it('renders the legacy-run lock reason and disables the quantity field too', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }), OVER_SHORTFALL, {
      lockReason: 'Legacy run - read only. Create a new plan to decide.',
    });
    expect(screen.getByTestId('decision-lock-reason')).toHaveTextContent(
      'Legacy run - read only. Create a new plan to decide.',
    );
    expect(screen.getByLabelText(/Order quantity/i)).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Record decision' })).toBeDisabled();
  });

  it('renders no lock reason and an actionable save when the run accepts the decision', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    expect(screen.queryByTestId('decision-lock-reason')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Record decision' })).not.toBeDisabled();
  });
});

describe('OrderDecisionSheet - split back to locations (AC-F08 / AC-F12)', () => {
  const SAVED_RESULT: OrderSummaryDecisionResult = {
    product_code: 'B2155-NL-BLUE',
    chosen_qty: 600,
    suggested_qty: 300,
    chosen_supplier_code: 'GDS',
    chosen_supplier_name: 'Guangdong Sanitary Ware',
    decided_by: 'Loo Keng Hoe',
    decided_at: '2026-08-03T10:14:00',
    location_allocations: [
      { warehouse_code: 'BRW', warehouse_name: 'Bandar Baru Warehouse', allocated_qty: 400 },
      { warehouse_code: 'JB', warehouse_name: 'Johor Bahru Branch', allocated_qty: 200 },
    ],
  };

  it('renders the returned location split the moment a decision is recorded', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }), OVER_SHORTFALL, { saved: SAVED_RESULT });
    expect(screen.getByText('Split back to locations')).toBeInTheDocument();
    expect(screen.getByTestId('split-BRW')).toHaveTextContent('BRW');
    expect(screen.getByTestId('split-BRW')).toHaveTextContent('400');
    expect(screen.getByTestId('split-JB')).toHaveTextContent('200');
    // The quantities sum EXACTLY to the chosen total.
    expect(screen.getByText('Total').closest('div')).toHaveTextContent('600');
  });

  it('closes the field and swaps the footer to Close / Recorded once saved', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }), OVER_SHORTFALL, { saved: SAVED_RESULT });
    expect(screen.getByLabelText(/Order quantity/i)).toBeDisabled();
    // "Close" is ambiguous with the sheet's own sr-only dismiss button, so match the
    // footer's visible-text one specifically.
    expect(screen.getByText('Close', { selector: 'button' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Recorded' })).toBeDisabled();
  });

  it('states there is nothing to split when the plan holds no location facts for the product', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }), OVER_SHORTFALL, {
      saved: { ...SAVED_RESULT, location_allocations: [] },
    });
    expect(
      screen.getByText(
        'This plan holds no location facts for the product, so there is nothing to split the quantity across.',
      ),
    ).toBeInTheDocument();
  });

  it('renders no split section before a decision has been recorded', () => {
    renderSheet(state({ data: BLUE_SUPPLIERS }));
    expect(screen.queryByText('Split back to locations')).not.toBeInTheDocument();
  });
});
