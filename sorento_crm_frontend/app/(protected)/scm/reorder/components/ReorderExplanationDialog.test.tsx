import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { ReorderRecommendation } from '../types/reorder.types';
import { ReorderExplanationDialog } from './ReorderExplanationDialog';

// RecordNavigation (the in-popup pager) calls useRouter().
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// M5 semantic layer hooks are react-query-backed; this suite renders the dialog
// without a QueryClientProvider, so stub them to inert states. Phase-2 replaces
// this with real coverage of the explanation / advisory / Ask surfaces.
vi.mock('../hooks/useExplainer', () => ({
  useRecommendationExplanation: () => ({ data: undefined, isLoading: false, isError: false }),
  useRecommendationAdvisory: () => ({ data: { advisory: null } }),
  useAskRecommendation: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

// The Coverage Timeline panel is react-query-backed too, and its own states are
// covered in CoverageTimelinePanel.test.tsx. Here we only need to know WHICH row it
// was asked about, so the stepping test can prove it follows the pager.
const coverage = vi.hoisted(() => ({
  useCoverageTimeline: vi.fn(),
  useAcceptCoverageTransfer: vi.fn(),
}));
vi.mock('../hooks/useCoverage', () => coverage);
coverage.useCoverageTimeline.mockReturnValue({
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
});
coverage.useAcceptCoverageTransfer.mockReturnValue({ mutate: vi.fn(), isPending: false });

// jsdom polyfills for Radix Dialog / Tooltip.
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

function rec(over: Partial<ReorderRecommendation>): ReorderRecommendation {
  return {
    id: 'rec-1',
    type: 'buy',
    sku: 'ACC-CB9001',
    product_name: 'Ceramic Wash Basin',
    abc_class: 'A',
    xyz_class: 'X',
    warehouse_code: 'WH-KL',
    warehouse_name: 'Kuala Lumpur DC',
    is_network: false,
    allocation: null,
    order_qty: 4,
    recommended_qty: 3.2,
    reorder_point: 8,
    min_qty: null,
    max_qty: null,
    order_up_to: 10,
    net_position: 6,
    days_of_cover: 3,
    reason: 'reorder_point',
    reason_label: 'reorder_point: net 6 <= ROP 8',
    confidence: 'high',
    sample_size: 40,
    supplier: {
      supplier_code: 'SUP-ACME',
      supplier_name: 'Acme Sanitary Sdn Bhd',
      unit_cost: 42,
      lead_time_days: 2,
      composite_score: 88,
      is_primary: true,
    },
    alternatives: [],
    is_exception: false,
    disposition_action: null,
    transfer_flag: null,
    forecast_daily_demand: 1,
    lead_time_days: 2,
    lead_time_source: 'measured',
    safety_stock: 6,
    safety_stock_method: 'fixed_days',
    safety_stock_fallback: null,
    service_level: 0.95,
    safety_days: 7,
    review_days: 30,
    moq: 1,
    order_multiple: 2,
    policy_type: 'reorder_point',
    supplier_selection: 'primary',
    unit_cost: null,
    cash_impact: null,
    rank: null,
    rank_score: null,
    funding_status: null,
    days_to_stockout: null,
    rank_factors: [],
    ...over,
  };
}

describe('ReorderExplanationDialog', () => {
  it('explains a BUY recommendation with the step-by-step derivation', () => {
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);

    // The old deterministic one-liner headline is gone — the AI summary block is
    // now the sole top-of-dialog narrative (covered in the explainer suite).

    // every derivation step is spelled out
    expect(screen.getByText('Forecast demand')).toBeInTheDocument();
    expect(screen.getByText('Lead time')).toBeInTheDocument();
    expect(screen.getByText('Safety stock')).toBeInTheDocument();
    expect(screen.getByText('Order-up-to target')).toBeInTheDocument();
    expect(screen.getByText('Order quantity')).toBeInTheDocument();
    expect(screen.getByText('Runway')).toBeInTheDocument();

    // the ROP arithmetic is made explicit (demand × lead time + safety stock)
    const ropStep = screen.getAllByText('Reorder point')[0].parentElement?.parentElement;
    expect(ropStep?.textContent).toMatch(/1 × 2 \+ 6 = 8/);
    // and the order-qty arithmetic (order-up-to − net → rounded)
    const qtyStep = screen.getByText('Order quantity').parentElement?.parentElement;
    expect(qtyStep?.textContent).toMatch(/10 − 6/);

    // supplier + confidence sections render
    expect(screen.getByText('Acme Sanitary Sdn Bhd')).toBeInTheDocument();
    expect(screen.getByText('chosen')).toBeInTheDocument();
    expect(screen.getByText('High confidence')).toBeInTheDocument();
  });

  it('explains a DISPOSITION recommendation with the demand behind its days-of-cover', () => {
    render(
      <ReorderExplanationDialog
        rec={rec({
          type: 'disposition',
          sku: 'MX-SHOWER-CHR',
          product_name: 'Chrome Shower Mixer',
          order_qty: null,
          recommended_qty: null,
          reason: 'overstock',
          reason_label: 'overstock: 856 days of cover exceeds the ceiling',
          days_of_cover: 856,
          net_position: 1731,
          forecast_daily_demand: 0.08,
          xyz_class: 'Z',
          supplier: null,
          disposition_action: 'hold',
          transfer_flag: 'consider transfer MX-SHOWER-CHR WH-JB→WH-KL',
        })}
        open
        onOpenChange={() => {}}
      />,
    );

    expect(screen.getByText("Why it's flagged")).toBeInTheDocument();
    expect(screen.getByText('Overstock')).toBeInTheDocument();
    expect(screen.getByText('Suggested action')).toBeInTheDocument();
    expect(screen.getByText('Hold')).toBeInTheDocument();
    expect(
      screen.getByText(/consider transfer MX-SHOWER-CHR WH-JB→WH-KL/i),
    ).toBeInTheDocument();

    // The forecast demand that PRODUCED the days-of-cover is now surfaced
    // (value + /day + demand pattern), same row as the buy variant.
    expect(screen.getByText('Forecast demand')).toBeInTheDocument();
    // Days-of-cover is derived from it: net ÷ daily demand = 856 days.
    const docStep = screen.getByText('Runway').parentElement?.parentElement;
    expect(docStep?.textContent).toMatch(/1,731 ÷ 0\.08 \/day = 856 days/);

    // Still no buy-only maths on a disposition.
    expect(screen.queryByText('Order-up-to target')).not.toBeInTheDocument();
    expect(screen.queryByText('Supplier')).not.toBeInTheDocument();
  });

  it('renders a modal overlay so a click-away closes without falling through to the grid', () => {
    render(<ReorderExplanationDialog rec={rec({})} open onOpenChange={() => {}} />);
    // A modal Radix dialog mounts a backdrop overlay that captures outside clicks.
    expect(document.querySelector('[data-slot="dialog-overlay"]')).not.toBeNull();
  });

  it('steps to the next/previous recommendation in place via the pager', () => {
    const recs = [
      rec({ id: 'r1', sku: 'SKU-ONE' }),
      rec({ id: 'r2', sku: 'SKU-TWO' }),
      rec({ id: 'r3', sku: 'SKU-THREE' }),
    ];
    const onNavigate = vi.fn();
    const { rerender } = render(
      <ReorderExplanationDialog
        rec={recs[0]}
        open
        onOpenChange={() => {}}
        recs={recs}
        totalCount={3}
        pageItemOffset={0}
        onNavigate={onNavigate}
      />,
    );

    // Position counter shows "1 / 3" and Previous is disabled at the start.
    expect(screen.getByText('1 / 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /previous recommendation/i })).toBeDisabled();

    // Next steps forward WITHOUT closing (calls onNavigate with the neighbour).
    fireEvent.click(screen.getByRole('button', { name: /next recommendation/i }));
    expect(onNavigate).toHaveBeenCalledWith(recs[1]);

    // Re-render at the middle rec: both directions enabled, counter advances.
    rerender(
      <ReorderExplanationDialog
        rec={recs[1]}
        open
        onOpenChange={() => {}}
        recs={recs}
        totalCount={3}
        pageItemOffset={0}
        onNavigate={onNavigate}
      />,
    );
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /previous recommendation/i })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: /previous recommendation/i }));
    expect(onNavigate).toHaveBeenCalledWith(recs[0]);
  });

  it('asks for the STEPPED row when the pager moves, not the row the dialog opened on', () => {
    const recs = [
      rec({ id: 'r1', sku: 'SKU-ONE', warehouse_code: 'BRW-BB', reorder_point: 8 }),
      rec({ id: 'r2', sku: 'SKU-TWO', warehouse_code: 'MWH-IR', reorder_point: 0 }),
    ];
    const { rerender } = render(
      <ReorderExplanationDialog
        rec={recs[0]}
        open
        onOpenChange={() => {}}
        recs={recs}
        totalCount={2}
        pageItemOffset={0}
        onNavigate={vi.fn()}
      />,
    );
    expect(coverage.useCoverageTimeline).toHaveBeenLastCalledWith(
      expect.objectContaining({ product_code: 'SKU-ONE', pool_code: 'BRW-BB', floor: 8 }),
      true,
    );

    rerender(
      <ReorderExplanationDialog
        rec={recs[1]}
        open
        onOpenChange={() => {}}
        recs={recs}
        totalCount={2}
        pageItemOffset={0}
        onNavigate={vi.fn()}
      />,
    );
    expect(coverage.useCoverageTimeline).toHaveBeenLastCalledWith(
      expect.objectContaining({ product_code: 'SKU-TWO', pool_code: 'MWH-IR', floor: 0 }),
      true,
    );
  });

  it('renders the Coverage timeline section for a DISPOSITION row too, never hides it', () => {
    render(
      <ReorderExplanationDialog
        rec={rec({ type: 'disposition', supplier: null, disposition_action: 'hold' })}
        open
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByText('Coverage timeline')).toBeInTheDocument();
  });

  it('labels the ABC rank factor with the layman term "Value", not "ABC value" (M8-F4)', () => {
    render(
      <ReorderExplanationDialog
        rec={rec({
          rank: 1,
          rank_score: 0.8,
          cash_impact: 168,
          unit_cost: 42,
          rank_factors: [
            { key: 'urgency', weight: 0.4, value: 0.9, present: true },
            { key: 'abc', weight: 0.2, value: 1.0, present: true },
          ],
        })}
        open
        onOpenChange={() => {}}
      />,
    );
    // the "Why this rank" block renders the ABC factor as the plain-language "Value"
    expect(screen.getByText('Value')).toBeInTheDocument();
    // the jargon label never leaks to the UI
    expect(screen.queryByText(/ABC value/i)).not.toBeInTheDocument();
  });

  it('flags a no-supplier EXCEPTION and cannot size the order', () => {
    render(
      <ReorderExplanationDialog
        rec={rec({
          type: 'exception',
          order_qty: null,
          recommended_qty: null,
          is_exception: true,
          supplier: null,
          alternatives: [],
        })}
        open
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByText(/No supplier is linked to this SKU/i)).toBeInTheDocument();
    expect(screen.getByText('Forecast demand')).toBeInTheDocument(); // derivation still shown
  });
});

describe('ReorderExplanationDialog - why this supplier, and where its cost came from', () => {
  // > "should show the alternative supplier with its cost and why we chosen what we have
  // >  chose because it is cheaper"
  //
  // "Chosen by lowest cost" named the RULE. It never said which supplier was beaten or by
  // how much, which is the part a buyer is actually checking.

  const cheapest = (over: Partial<ReorderRecommendation> = {}) =>
    rec({
      supplier: {
        supplier_code: 'SUP-ACME',
        supplier_name: 'Acme Sanitary Sdn Bhd',
        unit_cost: 8,
        unit_cost_source: 'last_po',
        unit_cost_ref: '202606-S0024',
        unit_cost_at: '2026-06-01',
        lead_time_days: 30,
        composite_score: 70,
        is_primary: false,
      },
      alternatives: [
        {
          supplier_code: 'SUP-DEAR',
          supplier_name: 'Kaiping Kaixin',
          unit_cost: 12,
          unit_cost_source: 'contract',
          lead_time_days: 45,
          composite_score: 90,
          is_primary: true,
        },
      ],
      supplier_selection: 'lowest_cost',
      supplier_reason: {
        basis: 'lowest_cost',
        runner_up: 'Kaiping Kaixin',
        runner_up_cost: 12,
        saving_per_unit: 4,
      },
      ...over,
    });

  it('names the supplier it beat and the saving per unit', () => {
    render(<ReorderExplanationDialog rec={cheapest()} open onOpenChange={() => {}} />);

    expect(
      screen.getByText(/cheapest.*RM 4 per unit under Kaiping Kaixin/i),
    ).toBeInTheDocument();
  });

  it('lists the alternative with its own cost, so the comparison is checkable', () => {
    render(<ReorderExplanationDialog rec={cheapest()} open onOpenChange={() => {}} />);

    expect(screen.getByText('Kaiping Kaixin')).toBeInTheDocument();
    expect(screen.getAllByText(/RM 12/).length).toBeGreaterThan(0);
  });

  it('says the cost is what we last paid, and on which order', () => {
    // A price we paid and a price somebody typed carry different weight, and the buyer is
    // entitled to know which one is driving the cash impact.
    render(<ReorderExplanationDialog rec={cheapest()} open onOpenChange={() => {}} />);

    expect(screen.getByText(/last paid.*202606-S0024/i)).toBeInTheDocument();
  });

  it('claims no saving when the runner-up has no cost of its own', () => {
    // The gap to an unpriced supplier is unknowable, not infinite.
    const r = cheapest({
      supplier_reason: {
        basis: 'lowest_cost',
        runner_up: 'Kaiping Kaixin',
        runner_up_cost: null,
        saving_per_unit: null,
      },
    });
    render(<ReorderExplanationDialog rec={r} open onOpenChange={() => {}} />);

    expect(screen.queryByText(/per unit cheaper/i)).not.toBeInTheDocument();
  });

  it('does not call a lone supplier the cheapest', () => {
    const r = cheapest({
      alternatives: [],
      supplier_reason: { basis: 'only_supplier', runner_up: null, saving_per_unit: null },
    });
    render(<ReorderExplanationDialog rec={r} open onOpenChange={() => {}} />);

    expect(screen.getByText(/only supplier linked to this item/i)).toBeInTheDocument();
    expect(screen.queryByText(/cheapest/i)).not.toBeInTheDocument();
  });

  it('reads a free item as free, never as missing a cost', () => {
    // 637 lines in the order book record 0. Free is a price; it funds at zero and plans
    // like anything else.
    const r = cheapest({
      supplier: {
        supplier_code: 'SUP-ACME',
        supplier_name: 'Acme Sanitary Sdn Bhd',
        unit_cost: 0,
        unit_cost_source: 'last_po',
        unit_cost_ref: '202606-S0024',
        lead_time_days: 30,
        composite_score: 70,
        is_primary: false,
      },
      alternatives: [],
      supplier_reason: { basis: 'only_supplier', runner_up: null, saving_per_unit: null },
    });
    render(<ReorderExplanationDialog rec={r} open onOpenChange={() => {}} />);

    expect(screen.queryByText(/No supplier cost/i)).not.toBeInTheDocument();
  });
});
