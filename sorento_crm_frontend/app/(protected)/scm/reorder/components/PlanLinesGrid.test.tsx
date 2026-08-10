/**
 * One grid, every line, no budget.
 *
 * The six bands this replaces sorted the work for the buyer, and two of them delivered a
 * verdict - Within budget, Over budget - before the buyer had decided anything.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import type { PlanDecisionMap } from '../lib/planDecisions';
import { PlanLinesGrid } from './PlanLinesGrid';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
    addListener() {}, removeListener() {},
  });
}

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    product_id: 'p1', warehouse_id: 'w1', is_network: false, allocation: null,
    order_qty: 23, recommended_qty: 23, reorder_point: 0, min_qty: null, max_qty: null,
    order_up_to: 0, net_position: -23, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 0, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 0, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 0, review_days: 0,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 230, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [],
    on_hand: 1, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 24,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

function renderGrid(lines: PlanLine[], decisions: PlanDecisionMap = {}) {
  const onDecide = vi.fn();
  const onClear = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PlanLinesGrid lines={lines} decisions={decisions} onDecide={onDecide} onClear={onClear} />
    </QueryClientProvider>,
  );
  return { onDecide, onClear };
}

beforeEach(() => vi.clearAllMocks());

describe('PlanLinesGrid - one list', () => {
  it('shows every kind of line in the same table', () => {
    renderGrid([
      line({ id: 'a', sku: 'BUY-1' }),
      line({ id: 'b', sku: 'COV-1', type: 'covered', rank: 2 }),
      line({ id: 'c', sku: 'ALLOC-1', type: 'disposition', rank: 3 }),
    ]);
    expect(screen.getByText('BUY-1')).toBeInTheDocument();
    expect(screen.getByText('COV-1')).toBeInTheDocument();
    expect(screen.getByText('ALLOC-1')).toBeInTheDocument();
  });

  it('says what the plan found as a column, not as a section', () => {
    renderGrid([line({ id: 'b', type: 'covered' })]);
    expect(screen.getByText('Covered by stock')).toBeInTheDocument();
  });

  it('mentions no budget anywhere, because nothing is decided yet', () => {
    // The whole point of the restructure: a verdict the buyer has not earned must not appear.
    const { container } = { container: renderGrid([line()]) && document.body };
    expect(container.textContent).not.toMatch(/within budget|over budget/i);
  });
});

describe('PlanLinesGrid - the netting is on the row', () => {
  it('shows what is needed and each thing that offsets it', () => {
    // These were behind a popover, which is what made the netting feel like a decision taken
    // on the buyer's behalf. Distinct values so a match cannot be the wrong column.
    renderGrid([line({ rank: 7, outstanding_sales: 24, on_hand: 5, incoming_spo: 3,
                       outstanding_po: 2, order_qty: 14 })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('24')).toBeInTheDocument(); // needed
    expect(within(row).getByText('5')).toBeInTheDocument(); // on hand
    expect(within(row).getByText('3')).toBeInTheDocument(); // incoming
    expect(within(row).getByText('2')).toBeInTheDocument(); // on order
    expect(within(row).getByText('14')).toBeInTheDocument(); // suggested
  });

  it('shows a dash, not a zero, for a figure that is not on file', () => {
    renderGrid([line({ on_hand: null })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getAllByText('-').length).toBeGreaterThan(0);
  });

  it('never prints a number for a line it cannot price', () => {
    // The Status column names it once; the Cost cell shows a dash carrying the reason,
    // rather than repeating the words or - far worse - printing a zero.
    renderGrid([line({ unit_cost: null, cash_impact: null })]);
    expect(screen.getByText('No price')).toBeInTheDocument(); // the status badge
    expect(
      screen.getByTitle(/No price on file, so this line cannot be costed/i),
    ).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - deciding', () => {
  it('offers buy, use stock and skip on a purchasable line', () => {
    renderGrid([line()]);
    expect(screen.getByRole('button', { name: /^Buy$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Use stock/i })).toBeInTheDocument();
  });

  it('pre-fills the suggested quantity so agreeing is one click', () => {
    renderGrid([line()]);
    expect((screen.getByLabelText(/Quantity to buy for SKU-1/i) as HTMLInputElement).value).toBe('23');
  });

  it('records an edited quantity rather than the suggestion', () => {
    const { onDecide } = renderGrid([line()]);
    fireEvent.change(screen.getByLabelText(/Quantity to buy for SKU-1/i), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: /^Buy$/i }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' }), { kind: 'buy', qty: 24 });
  });

  it('never offers to buy an allocation', () => {
    // It is stock to move, not stock to order.
    renderGrid([line({ type: 'disposition' })]);
    expect(screen.queryByRole('button', { name: /^Buy$/i })).toBeNull();
    expect(screen.getByRole('button', { name: /Use stock/i })).toBeInTheDocument();
  });

  it('offers a whole number of units, never a fraction of one', () => {
    // order_qty is a demand rate times a horizon, so it is routinely fractional on real data
    // (2,407.677748 on the live run). Rounded up: down would under-buy a shortage we just
    // calculated.
    renderGrid([line({ order_qty: 2407.677748 })]);
    expect((screen.getByLabelText(/Quantity to buy for SKU-1/i) as HTMLInputElement).value).toBe('2408');
  });

  it('shows a settled line as settled, and lets it be reopened', () => {
    const { onClear } = renderGrid([line()], { r1: { kind: 'buy', qty: 23 } });
    expect(screen.getByText(/Buying 23/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Change/i }));
    expect(onClear).toHaveBeenCalled();
  });
});
