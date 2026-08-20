/**
 * One grid, every line, no budget.
 *
 * The six bands this replaces sorted the work for the buyer, and two of them delivered a
 * verdict - Within budget, Over budget - before the buyer had decided anything.
 */
import React, { useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import { planTotals, type PlanDecision, type PlanDecisionMap } from '../lib/planDecisions';
import { PlanLinesGrid } from './PlanLinesGrid';
import type { ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { coverForLine, NO_COVER, type CoverSource } from '../lib/coverPlan';
import type { PriceAdvice } from '../lib/priceAdvice';
import type { PoReceipt } from '../lib/poCover';
import type { TrajectoryEntry } from '../lib/trajectory';
import type { ProductEconomics } from '../lib/productHealth';

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
  trendFor?: (l: PlanLine) => TrajectoryEntry | undefined,
  economicsFor?: (l: PlanLine) => ProductEconomics | undefined,
  onDecideLifecycle?: (productId: string, decision: 'keep' | 'discontinue' | null) => void,
  secondaryActions?: ToolbarAction[],
) {
  const onDecide = vi.fn();
  const onClear = vi.fn();
  const coverFor = (l: PlanLine) => (l.purchasable ? coverForLine(l, free) : NO_COVER);
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
        trendFor={trendFor}
        economicsFor={economicsFor}
        onDecideLifecycle={onDecideLifecycle}
        secondaryActions={secondaryActions}
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

  it('mentions no budget anywhere, because nothing is decided yet', () => {
    // The whole point of the restructure: a verdict the buyer has not earned must not appear.
    const { container } = { container: renderGrid([line()]) && document.body };
    expect(container.textContent).not.toMatch(/within budget|over budget/i);
  });
});

describe('PlanLinesGrid - the netting is on the row', () => {
  it('shows what is needed and each thing that offsets it, named after the documents', () => {
    // These were behind a popover, which is what made the netting feel like a decision taken
    // on the buyer's behalf. Distinct values so a match cannot be the wrong column. The
    // headers are the AutoCount document names the buyer reconciles against (SO / SPO / PO),
    // not synonyms ("Needed" / "Incoming" / "On order").
    renderGrid([line({ rank: 7, outstanding_sales: 24, on_hand: 5, incoming_spo: 3,
                       outstanding_po: 2, order_qty: 14 })]);
    expect(screen.getByText('SO')).toBeInTheDocument();
    expect(screen.getByText('SPO')).toBeInTheDocument();
    expect(screen.getByText('PO')).toBeInTheDocument();
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('24')).toBeInTheDocument(); // SO (needed)
    expect(within(row).getByText('5')).toBeInTheDocument(); // on hand
    expect(within(row).getByText('3')).toBeInTheDocument(); // SPO (incoming)
    expect(within(row).getByText('2')).toBeInTheDocument(); // PO (on order)
    expect(within(row).getAllByText('14').length).toBeGreaterThan(0); // suggested qty
  });

  it('shows a dash, not a zero, for a figure that is not on file', () => {
    renderGrid([line({ on_hand: null })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getAllByText('-').length).toBeGreaterThan(0);
  });

  it('never prints a number for a line it cannot price', () => {
    // The Cost cell shows a dash carrying the reason, rather than printing a zero.
    renderGrid([line({ unit_cost: null, cash_impact: null })]);
    expect(
      screen.getByTitle(/No price on file, so this line cannot be costed/i),
    ).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - one Decision column, not two (user markup, 2026-08-12)', () => {
  // > "I want the decision and suggestion to be made in 1 place instead of going to
  // >  multiple places ... after I made it, I know which one has been made, which one
  // >  hasn't, so they can decide until all outstanding decisions are cleared."

  it('never renders a Status column', () => {
    renderGrid([line()]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).not.toContain('Status');
  });

  it('never renders a separate Suggested action column', () => {
    renderGrid([line()]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).not.toContain('Suggested action');
  });

  it('an undecided row leads with ONE prominent button carrying the full mix', () => {
    renderGrid([line({ order_qty: 1100 })]);
    const btn = screen.getByRole('button', { name: /Buy 1,100/ });
    expect(btn).toBeInTheDocument();
    // Loudest element in the row: the solid primary variant (filled background).
    expect(btn.className).toMatch(/bg-primary/);
  });

  it('a decided row goes quiet: past tense + Change, no loud button', () => {
    renderGrid([line({ order_qty: 1100 })], { r1: { buy: 1100 } });
    expect(screen.getByText('Bought 1,100')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Change/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Buy 1,100/ })).not.toBeInTheDocument();
  });

  it('undecided rows sort first, decided rows sink to the bottom, rank preserved within each', () => {
    renderGrid(
      [
        line({ id: 'a', sku: 'FIRST', rank: 1 }),
        line({ id: 'b', sku: 'SECOND', rank: 2 }),
        line({ id: 'c', sku: 'THIRD', rank: 3 }),
      ],
      { a: { buy: 23 } }, // only the highest-ranked line ('a') is decided
    );
    const skus = screen
      .getAllByText(/^(FIRST|SECOND|THIRD)$/)
      .map((el) => el.textContent);
    expect(skus).toEqual(['SECOND', 'THIRD', 'FIRST']);
  });

  it('honours a controlled decidedFilter prop, narrowing to undecided lines', () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlanLinesGrid
          lines={[
            line({ id: 'a', sku: 'DECIDED-1' }),
            line({ id: 'b', sku: 'UNDECIDED-1', rank: 2 }),
          ]}
          decisions={{ a: { buy: 23 } } as PlanDecisionMap}
          onDecide={vi.fn()}
          onClear={vi.fn()}
          decidedFilter="undecided"
          onDecidedFilterChange={vi.fn()}
          staleAfterDays={180}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByText('UNDECIDED-1')).toBeInTheDocument();
    expect(screen.queryByText('DECIDED-1')).not.toBeInTheDocument();
  });

  it('a manual-mode (reorder_level) line renders the same composition in the merged cell', () => {
    // The label comes off the same composition source regardless of policy basis, so this
    // is automatic - pinned so a future change to the ledger cannot quietly break it.
    renderGrid([line({ policy_type: 'reorder_level', reorder_level: 42, order_qty: 50 })]);
    expect(screen.getByRole('button', { name: /Buy 50/ })).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - the velocity evidence under the Trend pill', () => {
  it('shows the average daily rate, to one decimal', () => {
    renderGrid([line({ forecast_daily_demand: 20 })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('avg 20.0/day')).toBeInTheDocument();
  });

  it('formats a fractional rate to one decimal', () => {
    renderGrid([line({ forecast_daily_demand: 0.55 })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('avg 0.6/day')).toBeInTheDocument();
  });

  it('is absent when there is no measurable rate (null or zero)', () => {
    renderGrid([line({ forecast_daily_demand: null })]);
    let row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).queryByText(/avg .*\/day/)).not.toBeInTheDocument();

    renderGrid([line({ forecast_daily_demand: 0 })]);
    row = screen.getAllByText('SKU-1').at(-1)!.closest('tr') as HTMLElement;
    expect(within(row).queryByText(/avg .*\/day/)).not.toBeInTheDocument();
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

  it('ships net and runway hidden - computed steps, not decisions', () => {
    // The user's markup (2026-08-11): "I don't really need net and runway". They stay
    // available through the columns menu and inside the row-click derivation; by default
    // the row reads suggestion -> explanation without them.
    renderGrid([line()]);
    expect(screen.queryByRole('button', { name: /Explain net/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Explain runway/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Product one'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getAllByText(/Net position/i).length).toBeGreaterThan(0);
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
    fireEvent.click(screen.getByRole('button', { name: /Skip SKU-1/i }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('the "Explain order qty" trigger opens the ledger, not the old drill (S3)', () => {
    // The popover CONTENT changed (three blocks: THE LINE / COVER BEFORE BUYING / THE BUY)
    // while the trigger and its aria-label stayed put, so a buyer's muscle memory still
    // works. `PlanOrderQtyLedger.test.tsx` covers the content in depth; this pins that the
    // grid actually wires it up off the SAME cover/decision state the row uses.
    renderGrid([line({ recommended_qty: 23, on_hand: 1, incoming_spo: 0, outstanding_sales: 24 })]);
    fireEvent.click(screen.getByRole('button', { name: /Explain order qty for SKU-1/i }));
    expect(screen.getByText('The line')).toBeInTheDocument();
    expect(screen.getByText('Cover before buying')).toBeInTheDocument();
    expect(screen.getByText('The buy')).toBeInTheDocument();
    expect(screen.getByText('Net now')).toBeInTheDocument();
    expect(screen.getByText('Gap to line')).toBeInTheDocument();
  });

  it('a manual-mode (reorder_level) line shows the level, not the ROP formula', () => {
    renderGrid([
      line({ policy_type: 'reorder_level', reorder_level: 42, reorder_level_source: 'manual' }),
    ]);
    fireEvent.click(screen.getByRole('button', { name: /Explain order qty for SKU-1/i }));
    // The grid ALSO has a "Reorder level" column header - scope to the ledger popover
    // (identified by its own header) so the assertion is about the ledger, not the column.
    const ledger = screen.getByText(/^Order qty = /).parentElement as HTMLElement;
    expect(within(ledger).getByText('Reorder level')).toBeInTheDocument();
    expect(within(ledger).queryByText('Safety stock')).not.toBeInTheDocument();
  });

  it('the ledger Popover stays open across a decision toggle (Fix A, user feedback, 2026-08-12)', () => {
    // A real, STATEFUL harness - `decisions` is recomputed and re-passed on every decide,
    // exactly as `PlanLinesSection`/`usePlanLines` do it, and exactly the condition that
    // used to recreate every column's cell function and remount the ledger Popover closed.
    function StatefulHarness() {
      const [decisions, setDecisions] = useState<PlanDecisionMap>({});
      const lines = [
        line({ order_qty: 40, recommended_qty: 40, forecast_daily_demand: 2, review_days: 30 }),
      ];
      return (
        <PlanLinesGrid
          lines={lines}
          decisions={decisions}
          onDecide={(l, next) => setDecisions((d) => ({ ...d, [l.id]: next }))}
          onClear={(l) => setDecisions((d) => {
            const rest = { ...d };
            delete rest[l.id];
            return rest;
          })}
          staleAfterDays={180}
        />
      );
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <StatefulHarness />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Explain order qty for SKU-1/i }));
    expect(screen.getByText('The buy')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: 'Add 60' }));

    // The decision committed (the row re-rendered with a fresh `decisions` object) AND the
    // popover content is still mounted and open - the toggle no longer closes the popup.
    expect(screen.getByText('The buy')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'Added 60' })).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - deciding', () => {
  it('offers Accept with the whole mixture, Adjust, and Skip on a purchasable line', () => {
    renderGrid([line()]);
    expect(screen.getByRole('button', { name: /Buy 23/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Adjust the mix/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Skip SKU-1/i })).toBeInTheDocument();
  });

  it('Accept records the engine mixture in one click (S16)', () => {
    const { onDecide } = renderGrid([line()]);
    fireEvent.click(screen.getByRole('button', { name: /Buy 23/ }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' }), { buy: 23 });
  });

  it('Adjust records an edited mixture, each part bounded by what exists', () => {
    const { onDecide } = renderGrid([line()]);
    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    fireEvent.change(screen.getByLabelText('Units to buy'), { target: { value: '24' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));
    expect(onDecide).toHaveBeenCalledWith(expect.objectContaining({ id: 'r1' }), { buy: 24 });
  });

  it('offers a whole number of units, never a fraction of one', () => {
    renderGrid([line({ order_qty: 2407.677748 })]);
    expect(screen.getByRole('button', { name: /Buy 2,408/ })).toBeInTheDocument();
  });

  it('shows a settled line as settled, past tense, and lets it be reopened', () => {
    // Past tense IS the "made / not made" signal (user markup, 2026-08-12) - the numbers
    // alone would read exactly like the suggestion.
    const { onClear } = renderGrid([line()], { r1: { buy: 23 } });
    expect(screen.getAllByText(/Bought 23/).length).toBeGreaterThan(0);
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
    expect(screen.getAllByText('Buy 188').length).toBeGreaterThan(0);
  });

  it('keeps the button label short - the source moved to the hover table', () => {
    // The live BRW-IB case: nothing on hand HERE, but BRW-BB is holding some. Round 2: the
    // codes came OUT of the label (they grew with every location and pushed the buy figure
    // past the truncation) and live in the accept hover's breakdown table instead.
    renderGrid([line({ order_qty: 1 })], {}, elsewhere);
    expect(screen.getByRole('button', { name: /Accept for .*Stock 1$/ })).toBeInTheDocument();
    expect(screen.queryByText(/Stock 1 \(BRW-BB\)/)).not.toBeInTheDocument();
  });

  it('proposes the split as ONE button carrying both parts, never a sentence', () => {
    // The live DC1-BB case: 6 units exist anywhere else against a shortage of 188.
    // Structured is the user's own markup: "more structured and organized, instead of
    // like a sentence" - the button's own label is the structure now (verb, quantity,
    // repeated per part), not a multi-line prose block.
    renderGrid([line({ order_qty: 188 })], {}, elsewhere);
    const btn = screen.getByRole('button', { name: /Accept for .*Stock 6 \+ Buy 182/ });
    expect(btn).toHaveTextContent('Stock 6 + Buy 182');
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

  it('cannot adjust stock in when nothing is free anywhere', () => {
    renderGrid([line({ order_qty: 188, on_hand: 0 })]);
    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    expect(screen.getByLabelText('Units from stock')).toBeDisabled();
  });

  it('Accept records where the stock comes from, not just that stock was used', () => {
    const { onDecide } = renderGrid([line({ order_qty: 1 })], {}, elsewhere);
    fireEvent.click(screen.getByRole('button', { name: /Stock 1/ }));
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      expect.objectContaining({
        stock: expect.objectContaining({
          qty: 1,
          sources: [expect.objectContaining({ warehouse_code: 'BRW-BB', qty: 1 })],
        }),
      }),
    );
  });

  it('shows a settled cover with its source', () => {
    renderGrid([line()], {
      r1: {
        stock: { qty: 5, sources: [{ warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', qty: 5 }] },
      },
    } as PlanDecisionMap, elsewhere);
    expect(screen.getByText('Stock 5')).toBeInTheDocument();
  });

  it('warns when the only cover crosses the dealer/project boundary', () => {
    renderGrid([line({ order_qty: 2, segment: 'project' })], {}, [
      { warehouse_id: 'wh-D', warehouse_code: 'DEALER', segment: 'dealer', qty: 50 },
    ]);
    expect(screen.getByText(/crosses segment/i)).toBeInTheDocument();
  });
});

describe('PlanLinesGrid - a covered row leads with use-stock, never a default buy', () => {
  // The live SIM-P002 bug: rec_type=covered, "150 available in this pool covers 15
  // committed" - the row's own POOL, not another warehouse's free stock (the cross-
  // warehouse pool below is deliberately EMPTY, to pin that the covered row never needs it).
  const coveredLine = () =>
    line({
      id: 'r1', sku: 'COV-1', type: 'covered', order_qty: 15,
      warehouse_code: 'BRW', warehouse_name: 'Butterworth',
      covered_committed: 15, covered_available: 150,
      reason_label: '150 available in this pool covers 15 committed',
    });

  it("the decision cell's primary button is Stock, not Buy", () => {
    renderGrid([coveredLine()]);
    const stockButton = screen.getByRole('button', { name: /Stock 15/ });
    expect(stockButton).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Buy \d/ })).not.toBeInTheDocument();
  });

  it('accepting it records stock, not a buy, and attaches no money', () => {
    const { onDecide } = renderGrid([coveredLine()]);
    fireEvent.click(screen.getByRole('button', { name: /Stock 15/ }));
    const decision = onDecide.mock.calls[0][1] as PlanDecision;
    expect(decision.buy ?? 0).toBe(0);
    expect(decision.stock?.qty).toBe(15);

    const totals = planTotals([coveredLine()], { r1: decision } as PlanDecisionMap);
    expect(totals).toMatchObject({ buying: 0, usingStock: 1, units: 0, cost: 0 });
  });

  it('still proposes a partial buy when the pool falls short of the commitment', () => {
    renderGrid([
      line({
        id: 'r1', sku: 'COV-2', type: 'covered', order_qty: 15,
        warehouse_code: 'BRW', warehouse_name: 'Butterworth',
        covered_committed: 15, covered_available: 4,
      }),
    ]);
    const btn = screen.getByRole('button', { name: /Stock 4/ });
    expect(btn).toHaveTextContent('Buy 11');
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

  it('leads with the price to buy at, and the verdict rides under it', () => {
    renderGrid([line()], {}, [], () => stale);

    // The row's unit_cost (10, no currency on the fixture, so it reads as base) is the
    // headline; the verdict badge is the caveat under it.
    expect(screen.getByText('Ask new price')).toBeInTheDocument();
    expect(screen.getByText('RM 10.00')).toBeInTheDocument();
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
    pick('Order type', 'dealer');

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
    pick('Suggested price', 'stale');

    expect(screen.getByText('STALE-1')).toBeInTheDocument();
    expect(screen.queryByText('FRESH-1')).not.toBeInTheDocument();
  });
});

describe('the column story - result first, explanation after (2026-08-11 markup)', () => {
  const headerTexts = () =>
    screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');

  it('reads as chapters: what to do, why, the action, the money, the AutoCount pair', () => {
    renderGrid([line()]);
    const heads = headerTexts();
    // Exact match: "PO" is a substring of "SPO" and would find the wrong column.
    const at = (label: string) => heads.findIndex((h) => h.trim() === label);

    // Chapter 1: the result (Suggested qty) comes BEFORE the arithmetic that explains it.
    expect(at('Suggested qty')).toBeGreaterThan(at('Order type'));
    expect(at('SO')).toBeGreaterThan(at('Suggested qty'));
    expect(at('SPO')).toBeGreaterThan(at('On hand'));
    expect(at('PO')).toBeGreaterThan(at('SPO'));
    // Chapter 2: ONE Decision cell carries the suggestion AND takes it (merged, 2026-08-12).
    expect(at('Decision')).toBeGreaterThan(at('PO'));
    // Chapter 3: price and supplier first, the total they produce after.
    expect(at('Suggested price')).toBeGreaterThan(at('Decision'));
    expect(at('Suggested supplier')).toBeGreaterThan(at('Suggested price'));
    expect(at('Total cost')).toBeGreaterThan(at('Suggested supplier'));
    // Chapter 4: the AutoCount round-trip closes the row.
    expect(at('AutoCount level + qty')).toBeGreaterThan(at('Total cost'));
  });

  it('puts the order type right after the priority, before the product', () => {
    renderGrid([line()]);
    const heads = headerTexts();
    const orderType = heads.findIndex((h) => h.includes('Order type'));
    const product = heads.findIndex((h) => h.includes('Product'));
    expect(orderType).toBeGreaterThan(-1);
    expect(orderType).toBeLessThan(product);
  });

  it('names the suggested supplier on the row, with the case for them behind it', () => {
    renderGrid([line()]);
    expect(screen.getByText('Acme')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /why this supplier/i }));
    expect(screen.getByText(/only supplier linked to this product/i)).toBeInTheDocument();
    expect(screen.getByText(/our own purchase records only/i)).toBeInTheDocument();
  });
});

describe('the forecast advisory (2026-08-11 markup)', () => {
  const rising: TrajectoryEntry = {
    verdict: 'rising', recent_qty: 120, previous_qty: 90, change_pct: 33.33,
    year_ago_qty: null, year_change_pct: null, window_months: 12,
    months: [], customers: [], agents: [], agents_available: false,
  };

  it('puts the trend on the SO column, where the demand it judges lives', () => {
    renderGrid([line()], {}, [], undefined, undefined, () => rising);
    const so = screen.getByTitle(/Outstanding sales-order quantity/).closest('td') as HTMLElement;
    expect(within(so).getByText('Orders rising - consider more')).toBeInTheDocument();
  });

  it('advises how many more, and one click applies it as the decision with its reason', () => {
    const { onDecide } = renderGrid(
      [line({ order_qty: 100, recommended_qty: 100 })], {}, [], undefined, undefined,
      () => rising,
    );

    const chip = screen.getByRole('button', { name: /Consider 34 more - orders rose 33%/ });
    fireEvent.click(chip);
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'r1' }),
      { buy: 134, reason: 'Trend: orders rose 33%' },
    );
  });

  it('advises fewer on a falling book, and never advises on a holding one', () => {
    renderGrid(
      [line({ order_qty: 100, recommended_qty: 100 })], {}, [], undefined, undefined,
      () => ({ ...rising, verdict: 'falling', change_pct: -28.4 }),
    );
    expect(
      screen.getByRole('button', { name: /Consider 28 less - orders fell 28%/ }),
    ).toBeInTheDocument();
  });

  it('stays silent when the trend argues nothing', () => {
    renderGrid(
      [line({ order_qty: 100 })], {}, [], undefined, undefined,
      () => ({ ...rising, verdict: 'holding' as const }),
    );
    expect(screen.queryByText(/Consider \d+ (more|less)/)).not.toBeInTheDocument();
  });
});

describe('product health (2026-08-11 markup)', () => {
  const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
    product_id: 'p1', avg_sell_price: 100, sell_source: 'orders', sold_qty: 240,
    on_hand: 40, avg_monthly_out: 20, turnover_months: 2, no_movement: false,
    lifecycle_decision: null, lifecycle_decided_at: null,
    ...over,
  });
  const rising: TrajectoryEntry = {
    verdict: 'rising', recent_qty: 120, previous_qty: 90, change_pct: 33.33,
    year_ago_qty: null, year_change_pct: null, window_months: 12,
    months: [], customers: [], agents: [], agents_available: false,
  };

  it('closes the row with the margin the item really earns, and the amount behind it', () => {
    // rec fixture: unit_cost 10 vs sells 100 -> 90% margin, RM 90.00 margin amount.
    renderGrid([line()], {}, [], undefined, undefined, undefined, () => econ());
    expect(screen.getByText('Margin 90% (RM 90.00)')).toBeInTheDocument();
  });

  it('asks to consider discontinuing a dead product, with the whole case behind it', () => {
    const dead = econ({ no_movement: true, avg_monthly_out: 0, turnover_months: null,
                        sold_qty: 0, on_hand: 25 });
    renderGrid(
      [line()], {}, [], undefined, undefined,
      () => ({ ...rising, verdict: 'quiet' as const, change_pct: null }),
      () => dead,
    );

    // Click the cell's own trigger (the column header is also named "Product health").
    fireEvent.click(screen.getByText('Consider discontinuing'));
    // The verdict is named in one line and the case is the factor list under it - the
    // prose sentence and the AutoCount footer were removed (AC-5).
    expect(screen.getByText('Suggestion: Discontinue')).toBeInTheDocument();
    expect(screen.getByText(/nothing left this product/i)).toBeInTheDocument();
    expect(screen.queryByText(/marking it in AutoCount stays your job/i)).not.toBeInTheDocument();
  });

  it('a consider-more advisory on a thin margin carries the caveat in the same breath', () => {
    // Base cost 92 (cash 9200 over 100 units) vs sells 100 -> 8% margin, below the floor.
    renderGrid(
      [line({ order_qty: 100, recommended_qty: 100, unit_cost: 92, cash_impact: 9200 })],
      {}, [], undefined, undefined, () => rising, () => econ(),
    );

    expect(
      screen.getByRole('button', {
        name: /Consider 34 more - orders rose 33%, but margin only 8%/,
      }),
    ).toBeInTheDocument();
  });
});

describe('the discontinue decision and the MOQ gap (2026-08-11 markup)', () => {
  const econ = (over: Partial<ProductEconomics> = {}): ProductEconomics => ({
    product_id: 'p1', avg_sell_price: 100, sell_source: 'orders', sold_qty: 240,
    on_hand: 40, avg_monthly_out: 20, turnover_months: 2, no_movement: false,
    lifecycle_decision: null, lifecycle_decided_at: null,
    ...over,
  });

  it('offers Keep and Discontinue, and records the click', () => {
    const onLifecycle = vi.fn();
    const dead = econ({ no_movement: true, avg_monthly_out: 0, turnover_months: null,
                        sold_qty: 0, on_hand: 25 });
    renderGrid([line()], {}, [], undefined, undefined, undefined, () => dead, onLifecycle);

    fireEvent.click(screen.getByText('Consider discontinuing'));
    fireEvent.click(screen.getByRole('button', { name: 'Discontinue' }));
    expect(onLifecycle).toHaveBeenCalledWith('p1', 'discontinue');
  });

  it('shows the recorded answer on the row instead of asking again', () => {
    const decided = econ({ lifecycle_decision: 'discontinue',
                           lifecycle_decided_at: '2026-08-11T00:00:00' });
    renderGrid([line()], {}, [], undefined, undefined, undefined, () => decided);

    expect(screen.getByText('You chose: discontinue')).toBeInTheDocument();
    expect(screen.queryByText('Consider discontinuing')).not.toBeInTheDocument();
  });

  it('shows the MOQ and flags the pump-up with its sell-through odds', () => {
    // Need 20, MOQ 100: engine already floored the buy at 100. At 5/month the 80 extra
    // is 16 months of stock - the row says so and suggests the way out.
    renderGrid(
      [line({ order_qty: 100, recommended_qty: 20, moq: 100 })], {}, [],
      undefined, undefined, undefined, () => econ({ avg_monthly_out: 5 }),
    );

    const gapNote = screen.getByText(/\+80 extra ≈ 16 mo - promotion\?/);
    expect(gapNote.closest('div')).toHaveTextContent('100');
  });

  it('a dash when no MOQ is on file - absence, not zero', () => {
    renderGrid([line()]);
    expect(screen.getByTitle('No MOQ on file for this supplier')).toBeInTheDocument();
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

    const btn = screen.getByRole('button', { name: /PO 200/ });
    expect(btn).not.toHaveTextContent(/Buy \d/);

    fireEvent.click(btn);
    expect(onDecide).toHaveBeenCalledWith(expect.anything(), { po: 200 });
  });

  it('a partial PO leaves the remainder as the buy', () => {
    renderGrid(
      [line({ order_qty: 200, recommended_qty: 200 })], {}, [], undefined,
      () => [{ ...receipts[0], remaining: 120 }],
    );

    const btn = screen.getByRole('button', { name: /PO 120/ });
    expect(btn).toHaveTextContent('Buy 80');
  });

  it('incoming SPO is named as already counted, never offered twice', () => {
    renderGrid([line({ order_qty: 200, incoming_spo: 50 })]);

    expect(screen.getByText('50 arriving (SPO) already counted')).toBeInTheDocument();
    expect(screen.queryByText(/Use SPO/)).not.toBeInTheDocument();
  });
});

describe('the Reorder level and Reorder qty columns - the STORED figures, not the suggestion', () => {
  it('has its own headers, distinct from the AutoCount level suggestion column', () => {
    renderGrid([line()]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Reorder level');
    expect(heads).toContain('Reorder qty');
    expect(heads).toContain('AutoCount level + qty');
  });

  it("shows the buyer's own level and names it as the source", () => {
    renderGrid([line({ reorder_level: 42, master_reorder_level: 10, master_reorder_quantity: 24 })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByTitle('Source: buyer level')).toHaveTextContent('42');
    expect(
      within(row).getByTitle("AutoCount's own reorder quantity, as uploaded"),
    ).toHaveTextContent('24');
  });

  it('falls back to the AutoCount master level when the buyer has not set one', () => {
    renderGrid([line({ reorder_level: null, master_reorder_level: 10, master_reorder_quantity: null })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByTitle('Source: AutoCount master')).toHaveTextContent('10');
  });

  it('shows a dash, never a zero, when neither figure is on file', () => {
    renderGrid([line({ reorder_level: null, master_reorder_level: null, master_reorder_quantity: null })]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByTitle('Source: not set')).toHaveTextContent('-');
    expect(
      within(row).getByTitle("AutoCount's own reorder quantity, as uploaded"),
    ).toHaveTextContent('-');
  });
});

describe('PlanLinesGrid - secondaryActions (the removed tiles\' replacement entry points)', () => {
  // Order summary / Plan exceptions / PO worklist have no row on this grid to filter
  // to, so instead of a tile they are quiet links in this SAME toolbar row, next to
  // Filters / Columns / Export - never rendered unless the caller supplies them.

  it('renders nothing extra when no secondaryActions are supplied', () => {
    renderGrid([line()]);
    expect(screen.queryByRole('button', { name: /Actions/i })).not.toBeInTheDocument();
  });

  it('collapses the supplied links into a single quiet "Actions" overflow', () => {
    const onClick = vi.fn();
    renderGrid([line()], {}, [], undefined, undefined, undefined, undefined, undefined, [
      { key: 'order_summary', label: 'Order summary', onClick },
      { key: 'plan_exceptions', label: 'Plan exceptions', onClick: vi.fn() },
      { key: 'po_worklist', label: 'PO worklist', onClick: vi.fn() },
    ]);

    const trigger = screen.getByRole('button', { name: /Actions/i });
    // Radix opens on pointerdown, which jsdom does not synthesise from fireEvent.click.
    fireEvent.keyDown(trigger, { key: 'Enter' });

    expect(screen.getByRole('menuitem', { name: 'Order summary' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Plan exceptions' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'PO worklist' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('menuitem', { name: 'Order summary' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('PlanLinesGrid - product photo on the row (AC-7)', () => {
  // > "as IT I do not know what a product looks like"
  // The icon lives on the product cell, beside the demand and checklist drills, and it is
  // the ONLY thing on the row that says what the item is.

  function renderWithPhotos(
    lines: PlanLine[],
    hasPhotoFor?: (l: PlanLine) => boolean,
    photoStatus: 'idle' | 'loading' | 'ready' | 'error' = 'ready',
    onOpenPhoto?: () => void,
  ) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlanLinesGrid
          lines={lines}
          decisions={{}}
          onDecide={vi.fn()}
          onClear={vi.fn()}
          hasPhotoFor={hasPhotoFor}
          photoStatus={photoStatus}
          onOpenPhoto={onOpenPhoto}
          staleAfterDays={180}
        />
      </QueryClientProvider>,
    );
  }

  it('carries a photo icon on every row', () => {
    renderWithPhotos([line({ id: 'a', sku: 'BUY-1' }), line({ id: 'b', sku: 'BUY-2', rank: 2 })]);
    expect(screen.getAllByRole('button', { name: /product photo/i })).toHaveLength(2);
  });

  it('dims the icon for a product the run found no photo for', () => {
    renderWithPhotos(
      [line({ id: 'a', sku: 'HAS-1', product_id: 'p1' }),
       line({ id: 'b', sku: 'NONE-1', product_id: 'p2', rank: 2 })],
      (l) => l.product_id === 'p1',
    );

    const withPhoto = screen.getByText('HAS-1').closest('tr') as HTMLElement;
    const without = screen.getByText('NONE-1').closest('tr') as HTMLElement;

    expect(
      within(withPhoto).getByRole('button', { name: /product photo/i }).className,
    ).not.toContain('text-muted-foreground/50');
    expect(
      within(without).getByRole('button', { name: /product photo/i }).className,
    ).toContain('text-muted-foreground/50');
  });

  it('nothing is dimmed before the photos have been asked for', () => {
    // Dimming on `idle` would tell the buyer a product has no photo before anyone looked.
    renderWithPhotos([line({ sku: 'BUY-1' })], undefined, 'idle');
    expect(
      screen.getByRole('button', { name: /product photo/i }).className,
    ).not.toContain('text-muted-foreground/50');
  });

  it('starts the run-wide fetch on the FIRST icon opened, not on mount', () => {
    const onOpenPhoto = vi.fn();
    renderWithPhotos([line({ sku: 'BUY-1' })], undefined, 'idle', onOpenPhoto);

    expect(onOpenPhoto).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /product photo/i }));
    expect(onOpenPhoto).toHaveBeenCalledTimes(1);
  });
});

describe('PlanLinesGrid - product-grain channel grouping (5.3 follow-up, 19-20 Aug)', () => {
  // The captain's refined ask, superseding the first (product, channel) cut: 1 product
  // across 3 warehouses (1 bare-site Retail, 2 suffixed-bin Project) collapses into ONE
  // row per PRODUCT, with Project/Retail as dynamic COLUMNS on that single row - "instead
  // of 1 column SO, 1 column project, 1 column retail, it should be 2 columns".
  const retail = line({
    id: 'a', warehouse_id: 'w-brw', warehouse_code: 'BRW', warehouse_name: 'Butterworth',
    segment: 'dealer', rank: 1, order_qty: 3,
    retail_committed: 6, project_committed: 0, unclassified_committed: 0, project_need: 0,
  });
  const projectIb = line({
    id: 'b', warehouse_id: 'w-ib', warehouse_code: 'BRW-IB', warehouse_name: 'BRW - IB',
    segment: 'project', rank: 2, order_qty: 4,
    retail_committed: 0, project_committed: 5, unclassified_committed: 0, project_need: 3,
  });
  const projectIr = line({
    id: 'c', warehouse_id: 'w-ir', warehouse_code: 'BRW-IR', warehouse_name: 'BRW - IR',
    segment: 'project', rank: 3, order_qty: 5,
    retail_committed: 0, project_committed: 2, unclassified_committed: 0, project_need: 1,
  });

  function renderGroupedGrid(
    lines: PlanLine[],
    channelTrendFor?: (productId: string | null, channel: 'project' | 'retail' | 'unclassified') =>
      { verdict: 'rising' | 'holding' | 'falling' | 'quiet' | 'no_history'; recent_qty: number;
        previous_qty: number; change_pct: number | null; window_months: number;
        avg_day: number | null } | undefined,
  ) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlanLinesGrid
          lines={lines}
          decisions={{}}
          onDecide={vi.fn()}
          onClear={vi.fn()}
          groupByChannel
          decisionsReadOnly
          readOnlyReason="Decided at Product grain"
          channelTrendFor={channelTrendFor}
          staleAfterDays={180}
        />
      </QueryClientProvider>,
    );
  }

  it('an ungrouped (Location-grain) plan renders the fixture exactly as before: 3 rows', () => {
    renderGrid([retail, projectIb, projectIr]);
    expect(screen.getAllByText('SKU-1')).toHaveLength(3);
    expect(screen.getByText('Butterworth')).toBeInTheDocument();
    expect(screen.getByText('BRW - IB')).toBeInTheDocument();
    expect(screen.getByText('BRW - IR')).toBeInTheDocument();
  });

  it('an ungrouped plan still carries the Order-type badge and the fixed SO/channel columns', () => {
    renderGrid([retail]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Order type');
    expect(heads.some((h) => h.includes('SO'))).toBe(true);
  });

  it('collapses all 3 rows of the same product into a SINGLE row once grouped', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    expect(screen.getAllByText('SKU-1')).toHaveLength(1);
  });

  it('grouped mode has no Location column - the expand carries the locations instead (captain, 19-20 Aug: "i don\'t need locations column")', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).not.toContain('Location');
    expect(screen.queryByText('Butterworth, BRW - IB, BRW - IR')).not.toBeInTheDocument();
  });

  it('an ungrouped (Location-grain) plan keeps the Location column', () => {
    renderGrid([retail]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Location');
  });

  it('grouped mode drops the Order-type badge column and the SO/Project/Retail/Unclassified fixed columns', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).not.toContain('Order type');
    expect(heads).not.toContain('SO');
    expect(heads).not.toContain('Unclass.');
  });

  it('renders dynamic channel columns off what is actually present - Project and Retail here', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Project');
    expect(heads).toContain('Retail');
    expect(heads).not.toContain('Unclassified');
  });

  it('each channel column shows that channel\'s open demand, summed across the product\'s locations', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('7')).toBeInTheDocument(); // project: 0 + 5 + 2
    expect(within(row).getByText('6')).toBeInTheDocument(); // retail: 6 + 0 + 0
  });

  it('the channel column carries a trend subline sourced from channelTrendFor, per channel', () => {
    const channelTrendFor = vi.fn((productId: string | null, channel: string) =>
      channel === 'project'
        ? { verdict: 'rising' as const, recent_qty: 10, previous_qty: 5, change_pct: 100,
            window_months: 12, avg_day: 2.5 }
        : undefined,
    );
    renderGroupedGrid([retail, projectIb, projectIr], channelTrendFor);
    expect(channelTrendFor).toHaveBeenCalledWith('p1', 'project');
    expect(screen.getByText(/Orders rising - consider more/)).toBeInTheDocument();
    expect(screen.getByText(/avg 2.5\/day/)).toBeInTheDocument();
  });

  it('sums order qty across the group\'s warehouses', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('12')).toBeInTheDocument(); // 3 + 4 + 5
  });

  it('expanding the group row reveals its 3 underlying per-warehouse rows', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    expect(screen.queryByText('BRW - IB')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByText('Butterworth')).toBeInTheDocument();
    expect(screen.getByText('BRW - IB')).toBeInTheDocument();
    expect(screen.getByText('BRW - IR')).toBeInTheDocument();
  });

  it('the expand hides a location whose every figure is zero (captain, 19-20 Aug: "if 0 quantity why show here")', () => {
    const allZero = line({
      id: 'z', warehouse_id: 'w-zero', warehouse_code: 'BRW-Z', warehouse_name: 'Zero Loc',
      segment: 'dealer', rank: 5, order_qty: 0, on_hand: 0, incoming_spo: 0, outstanding_po: 0,
      outstanding_sales: 0, project_need: 0, retail_need: 0, unclassified_need: 0,
    });
    renderGroupedGrid([retail, projectIb, projectIr, allZero]);
    fireEvent.click(screen.getByText('SKU-1'));
    expect(screen.getByText('Butterworth')).toBeInTheDocument();
    expect(screen.getByText('BRW - IB')).toBeInTheDocument();
    expect(screen.getByText('BRW - IR')).toBeInTheDocument();
    expect(screen.queryByText('Zero Loc')).not.toBeInTheDocument();
  });

  it('never empties the expand entirely - every member is shown when ALL of them are zero', () => {
    const allZero1 = line({
      id: 'z1', product_id: 'p9', sku: 'SKU-ZERO', warehouse_id: 'w-z1', warehouse_name: 'Zero 1',
      segment: 'dealer', rank: 5, order_qty: 0, on_hand: 0, incoming_spo: 0, outstanding_po: 0,
      outstanding_sales: 0, project_need: 0, retail_need: 0, unclassified_need: 0,
    });
    const allZero2 = line({
      id: 'z2', product_id: 'p9', sku: 'SKU-ZERO', warehouse_id: 'w-z2', warehouse_name: 'Zero 2',
      segment: 'dealer', rank: 6, order_qty: 0, on_hand: 0, incoming_spo: 0, outstanding_po: 0,
      outstanding_sales: 0, project_need: 0, retail_need: 0, unclassified_need: 0,
    });
    renderGroupedGrid([allZero1, allZero2]);
    fireEvent.click(screen.getByText('SKU-ZERO'));
    expect(screen.getByText('Zero 1')).toBeInTheDocument();
    expect(screen.getByText('Zero 2')).toBeInTheDocument();
  });

  it('a grouped row falls back to the product master reorder level/qty when nobody has set the buyer\'s own (19-20 Aug follow-up, captain: SRTWCX8861-S)', () => {
    const withMaster = line({
      id: 'm', warehouse_id: 'w-master', segment: 'dealer', rank: 6,
      master_reorder_level: 10, master_reorder_quantity: 50,
    });
    renderGroupedGrid([withMaster]);
    const row = screen.getByText('SKU-1').closest('tr') as HTMLElement;
    expect(within(row).getByText('10')).toBeInTheDocument();
    expect(within(row).getByText('50')).toBeInTheDocument();
  });

  it('a group row is always read-only', () => {
    renderGroupedGrid([retail, projectIb, projectIr]);
    expect(screen.getAllByTestId(/^decision-read-only-group:/)).toHaveLength(1);
    expect(screen.getAllByText('Decided at Product grain')).toHaveLength(1);
  });

  it('a warehouse with no persisted segment still folds into the SAME group row, adding an Unclassified column', () => {
    const unmapped = line({
      id: 'd', sku: 'SKU-1', warehouse_id: 'w-x', warehouse_code: 'WHX', warehouse_name: 'Unmapped',
      segment: null, rank: 4, unclassified_committed: 1,
    });
    renderGroupedGrid([retail, unmapped]);
    expect(screen.getAllByText('SKU-1')).toHaveLength(1);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Unclassified');
  });

  it('an ungrouped-mode plan keeps the fixed SO/Project/Retail/Unclassified need columns, not the dynamic channel ones', () => {
    // Ungrouped mode has its own "Project"/"Retail" headers too (the fixed `project_need`
    // / `retail_need` columns) - what distinguishes grouped mode is `Order type` being
    // absent and `Unclass.` present, both pinned in the earlier assertions above.
    renderGrid([retail]);
    const heads = screen.getAllByRole('columnheader').map((h) => h.textContent ?? '');
    expect(heads).toContain('Order type');
    expect(heads).toContain('Unclass.');
  });
});
