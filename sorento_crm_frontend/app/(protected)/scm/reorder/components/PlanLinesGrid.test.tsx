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
import { proposeCover, NO_COVER, type CoverSource } from '../lib/coverPlan';
import type { PriceAdvice } from '../lib/priceAdvice';
import type { PoReceipt } from '../lib/poCover';

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

// The filter popover uses the standard SearchableSelect. Mock it as a native <select> so
// the options are in the DOM without driving a cmdk popover - the assertions here are
// about which ROWS survive a filter, not about popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options = [],
    placeholder,
  }: {
    value?: string;
    onChange?: (v: string) => void;
    options?: Array<{ value: string; label: string }>;
    placeholder?: string;
  }) => (
    <select
      aria-label={placeholder}
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

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

function renderGrid(
  lines: PlanLine[],
  decisions: PlanDecisionMap = {},
  free: CoverSource[] = [],
  priceFor?: (l: PlanLine) => PriceAdvice | undefined,
  poFor?: (l: PlanLine) => PoReceipt[],
) {
  const onDecide = vi.fn();
  const onClear = vi.fn();
  const coverFor = (l: PlanLine) =>
    l.purchasable
      ? proposeCover(Math.ceil(l.order_qty), l.warehouse_id ?? null, l.rec.segment ?? null, free)
      : NO_COVER;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PlanLinesGrid
        lines={lines}
        decisions={decisions}
        onDecide={onDecide}
        onClear={onClear}
        coverFor={coverFor}
        priceFor={priceFor}
        poFor={poFor}
        staleAfterDays={180}
      />
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

describe('PlanLinesGrid - the explanations are still there', () => {
  // Every one of these was on the old hand-rolled row and got dropped when the grid was
  // rebuilt. They are the reason a computed quantity is trustworthy rather than taken on
  // faith, so they are pinned here.
  it('offers the demand and checklist drills beside the product', () => {
    renderGrid([line()]);
    expect(screen.getByRole('button', { name: /Demand behind this row/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /What the plan checked/i })).toBeInTheDocument();
  });

  it('explains how the suggested quantity was reached', () => {
    renderGrid([line()]);
    expect(
      screen.getByRole('button', { name: /Explain order qty for SKU-1/i }),
    ).toBeInTheDocument();
  });

  it('explains the net and the runway', () => {
    renderGrid([line()]);
    expect(screen.getByRole('button', { name: /Explain net/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Explain runway/i })).toBeInTheDocument();
  });

  it('opens the full derivation when the row itself is clicked', () => {
    renderGrid([line()]);
    fireEvent.click(screen.getByText('Product one'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('does NOT open it when the decision controls are used', () => {
    // The row handler is given the row, not the event, so it cannot tell them apart by
    // itself: adjusting a quantity would otherwise throw the dialog over your work.
    renderGrid([line()]);
    fireEvent.click(screen.getByLabelText(/Quantity to buy for SKU-1/i));
    expect(screen.queryByRole('dialog')).toBeNull();
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

describe('PlanLinesGrid - buy, cover, or both', () => {
  const elsewhere: CoverSource[] = [
    { warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', segment: 'project', qty: 5 },
    { warehouse_id: 'wh-PJ-SR', warehouse_code: 'PJ-SR', segment: 'project', qty: 1 },
  ];

  it('says buy when no other location holds any', () => {
    renderGrid([line({ order_qty: 188 })]);
    expect(screen.getByText('Buy 188')).toBeInTheDocument();
  });

  it('names the source when stock elsewhere covers it outright', () => {
    // The live BRW-IB case: nothing on hand HERE, but BRW-BB is holding some.
    renderGrid([line({ order_qty: 1 })], {}, elsewhere);
    expect(screen.getByText('Use stock 1 from BRW-BB')).toBeInTheDocument();
  });

  it('proposes the split as structured parts, one per line, never a sentence', () => {
    // The live DC1-BB case: 6 units exist anywhere else against a shortage of 188.
    // Structured is the user's own markup: "more structured and organized, instead of
    // like a sentence".
    renderGrid([line({ order_qty: 188 })], {}, elsewhere);
    expect(screen.getByText('Use stock 5 from BRW-BB, 1 from PJ-SR')).toBeInTheDocument();
    expect(screen.getByText('Buy 182')).toBeInTheDocument();
  });

  it('says when the engine is superseding CS on a project line', () => {
    // Purchasing can overrule the inquiry, but never silently: a quiet disagreement with
    // CS reads as the engine miscounting.
    renderGrid([line({ order_qty: 188, segment: 'project' })], {}, elsewhere);
    expect(screen.getByText('CS asked to buy 188')).toBeInTheDocument();
  });

  it('does not claim CS asked for anything on a retail line', () => {
    renderGrid([line({ order_qty: 188, segment: 'dealer' })], {}, elsewhere);
    expect(screen.queryByText(/CS asked/)).not.toBeInTheDocument();
  });

  it('refuses Use stock when nothing is free anywhere, and says why', () => {
    // The reported bug: the button was offered on a row with nothing behind it.
    renderGrid([line({ order_qty: 188, on_hand: 0 })]);
    const btn = screen.getByRole('button', { name: /Use stock/i });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', expect.stringMatching(/No free stock at another location/i));
  });

  it('records where the stock comes from, not just that stock was used', () => {
    const { onDecide } = renderGrid([line({ order_qty: 1 })], {}, elsewhere);
    fireEvent.click(screen.getByRole('button', { name: /Use stock/i }));
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      expect.objectContaining({
        kind: 'use_stock',
        sources: [expect.objectContaining({ warehouse_code: 'BRW-BB', qty: 1 })],
      }),
    );
  });

  it('shows a settled cover with its source', () => {
    renderGrid([line()], {
      r1: {
        kind: 'use_stock',
        sources: [{ warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', qty: 5 }],
      },
    } as PlanDecisionMap, elsewhere);
    expect(screen.getByText(/Using stock 5 from BRW-BB/)).toBeInTheDocument();
  });

  it('warns when the only cover crosses the dealer/project boundary', () => {
    renderGrid([line({ order_qty: 2, segment: 'project' })], {}, [
      { warehouse_id: 'wh-D', warehouse_code: 'DEALER', segment: 'dealer', qty: 50 },
    ]);
    expect(screen.getByText(/crosses segment/i)).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - what price to use', () => {
  const stale: PriceAdvice = {
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
  };

  it('puts the age of the price on the row, beside what it costs', () => {
    renderGrid([line()], {}, [], () => stale);

    expect(screen.getByText('Ask new price')).toBeInTheDocument();
    expect(screen.getByText(/USD 20\.37/)).toBeInTheDocument();
  });

  it('leaves the cell empty when there is no price opinion, rather than implying all is well', () => {
    renderGrid([line()], {}, [], () => undefined);

    expect(screen.queryByText('Ask new price')).not.toBeInTheDocument();
    expect(screen.queryByText('Use last price')).not.toBeInTheDocument();
  });

  it('opening the price does not also open the row dialog', () => {
    // `onRowClick` is handed the row, not the event, so an interactive cell that does not
    // stop propagation opens the derivation dialog on top of what the buyer was reading.
    renderGrid([line()], {}, [], () => stale);
    fireEvent.click(screen.getByRole('button', { name: /price history/i }));

    // The popover itself carries role="dialog", so the check is that ONE opened and not two.
    expect(screen.getByText(/ask for a fresh quote/i)).toBeInTheDocument();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
  });
});

describe('the suggestion filters (S14)', () => {
  const openFilters = () => {
    // Radix DropdownMenu opens on pointerdown, not click.
    fireEvent.pointerDown(screen.getByRole('button', { name: /^Filters/ }), {
      button: 0,
      ctrlKey: false,
    });
  };
  const pick = (placeholder: string, value: string) => {
    fireEvent.change(screen.getByLabelText(placeholder), { target: { value } });
  };

  it('filters to one side of the business', () => {
    renderGrid([
      line({ id: 'p', sku: 'PROJ-1', segment: 'project' }),
      line({ id: 'd', sku: 'DEAL-1', segment: 'dealer' }),
    ]);
    openFilters();
    pick('Side', 'dealer');

    expect(screen.getByText('DEAL-1')).toBeInTheDocument();
    expect(screen.queryByText('PROJ-1')).not.toBeInTheDocument();
  });

  it('filters by the price answer', () => {
    const advice: PriceAdvice = {
      advice: 'stale',
      last: { po_number: null, issue_date: '2020-01-01', unit_cost: 5, currency: 'USD', qty: 1 },
      previous: null, age_days: 2000, movement_pct: null, currency_changed: false,
      standing_cost: 5, standing_currency: 'USD', standing_gap_pct: null,
      free_of_charge_lines: 0,
    };
    renderGrid(
      [line({ id: 'a', sku: 'STALE-1' }), line({ id: 'b', sku: 'FRESH-1' })],
      {},
      [],
      (l) => (l.sku === 'STALE-1' ? advice : { ...advice, advice: 'recent', age_days: 10 }),
    );
    openFilters();
    pick('Price to use', 'stale');

    expect(screen.getByText('STALE-1')).toBeInTheDocument();
    expect(screen.queryByText('FRESH-1')).not.toBeInTheDocument();
  });
});

describe('the PO book offsets the buy (S15)', () => {
  const receipts: PoReceipt[] = [
    { po_number: 'PO-2026/07-0002', status: 'active', expected_date: '2026-08-10', remaining: 504 },
  ];

  it('a PO that covers the shortage replaces the buy with "Use PO"', () => {
    const { onDecide } = renderGrid(
      [line({ order_qty: 200, recommended_qty: 200 })], {}, [], undefined, () => receipts,
    );

    expect(screen.getByText('Use PO 200 - already ordered')).toBeInTheDocument();
    expect(screen.queryByText(/^Buy /)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Use PO' }));
    expect(onDecide).toHaveBeenCalledWith(expect.anything(), { kind: 'use_po', qty: 200 });
  });

  it('a partial PO leaves the remainder as the buy', () => {
    renderGrid(
      [line({ order_qty: 200, recommended_qty: 200 })], {}, [], undefined,
      () => [{ ...receipts[0], remaining: 120 }],
    );

    expect(screen.getByText('Use PO 120 - already ordered')).toBeInTheDocument();
    expect(screen.getByText('Buy 80')).toBeInTheDocument();
  });

  it('incoming SPO is named as already counted, never offered twice', () => {
    renderGrid([line({ order_qty: 200, incoming_spo: 50 })]);

    expect(screen.getByText('50 arriving (SPO) already counted')).toBeInTheDocument();
    expect(screen.queryByText(/Use SPO/)).not.toBeInTheDocument();
  });
});
