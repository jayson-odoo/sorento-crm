/**
 * The decision cell: one short label on the button, the detail in a hover table (AC-3.1).
 *
 * Round 2 of the captain's review: the label used to carry the source codes ("Stock 15
 * (BRW-BB, PJ-SR) + Buy 182"), which grew with every location and truncated before the buy
 * figure - the one number the button is asking about. The codes moved to the hover table.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';
import { coverForLine, NO_COVER, type CoverProposal, type CoverSource } from '../lib/coverPlan';
import { recToPlanLine, type PlanLine } from '../lib/planLine';
import type { PlanDecision } from '../lib/planDecisions';
import type { ReorderRecommendation } from '../types/reorder.types';
import { PlanLineDecisionCell } from './PlanLineDecisionCell';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});

function rec(over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id: 'r1', type: 'buy', sku: 'SKU-1', product_name: 'Product one',
    abc_class: null, xyz_class: null, warehouse_code: 'DC1-BB', warehouse_name: 'DC1',
    product_id: 'p1', warehouse_id: 'wh-DC1-BB', is_network: false, allocation: null,
    order_qty: 188, recommended_qty: 188, reorder_point: 74, min_qty: null, max_qty: null,
    order_up_to: 134, net_position: -188, days_of_cover: null, reason: 'reorder_point',
    reason_label: '', confidence: 'low', sample_size: 0,
    supplier: { supplier_code: 'S1', supplier_name: 'Acme', unit_cost: 10,
                lead_time_days: 30, composite_score: 0, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 2, lead_time_days: 30, lead_time_source: 'default',
    safety_stock: 7, safety_stock_method: null, safety_stock_fallback: null,
    service_level: null, safety_days: 7, review_days: 30, demand_window_days: 90,
    moq: null, order_multiple: null, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 10, cash_impact: 1880, rank: 1, rank_score: 0, funding_status: null,
    days_to_stockout: null, rank_factors: [], segment: 'project',
    on_hand: 0, incoming_spo: 0, outstanding_po: 0, outstanding_sales: 188,
    reorder_level: null, master_reorder_level: null,
    ...over,
  } as ReorderRecommendation;
}

const line = (over: Partial<ReorderRecommendation> = {}): PlanLine => recToPlanLine(rec(over));

const elsewhere: CoverSource[] = [
  { warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', segment: 'project', qty: 5 },
  { warehouse_id: 'wh-PJ-SR', warehouse_code: 'PJ-SR', segment: 'project', qty: 1 },
];

function renderCell(over: {
  line?: PlanLine;
  decision?: PlanDecision;
  cover?: CoverProposal;
  mixed?: boolean;
  onDecide?: (next: PlanDecision) => Promise<void> | void;
  onClear?: () => Promise<void> | void;
} = {}) {
  // Always a real `Mock` (wrapping any override), never a plain function - every existing
  // test reads `.mock.calls` off the returned handles.
  const onDecide = over.onDecide ? vi.fn(over.onDecide) : vi.fn();
  const onClear = over.onClear ? vi.fn(over.onClear) : vi.fn();
  const l = over.line ?? line();
  render(
    <PlanLineDecisionCell
      line={l}
      decision={over.decision}
      mixed={over.mixed}
      cover={over.cover ?? NO_COVER}
      onDecide={onDecide}
      onClear={onClear}
    />,
  );
  return { onDecide, onClear, line: l };
}

beforeEach(() => vi.clearAllMocks());

describe('PlanLineDecisionCell - the label stays short', () => {
  it('carries both parts and no source codes on a split', () => {
    const l = line();
    renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    const btn = screen.getByRole('button', { name: /Accept for SKU-1/ });
    expect(btn).toHaveTextContent('Stock 6 + Buy 182');
    expect(btn).not.toHaveTextContent('BRW-BB');
  });

  it('reads as one part when the other is zero', () => {
    const l = line({ order_qty: 1778, recommended_qty: 1778, outstanding_sales: 1778 });
    renderCell({ line: l, cover: coverForLine(l, []) });
    expect(screen.getByRole('button', { name: /Accept for SKU-1/ })).toHaveTextContent('Buy 1,778');
  });

  it('reads as stock alone when nothing needs buying', () => {
    const l = line({ order_qty: 4, recommended_qty: 4, outstanding_sales: 4 });
    renderCell({ line: l, cover: coverForLine(l, elsewhere) });
    const btn = screen.getByRole('button', { name: /Accept for SKU-1/ });
    expect(btn).toHaveTextContent('Stock 4');
    expect(btn).not.toHaveTextContent('Buy');
  });
});

describe('PlanLineDecisionCell - accepting records the split', () => {
  it('records where the stock comes from, at the proposed quantities', () => {
    const l = line();
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Accept for SKU-1/ }));
    expect(onDecide).toHaveBeenCalledWith(
      expect.objectContaining({
        buy: 182,
        stock: expect.objectContaining({
          qty: 6,
          sources: [
            expect.objectContaining({ warehouse_code: 'BRW-BB', qty: 5 }),
            expect.objectContaining({ warehouse_code: 'PJ-SR', qty: 1 }),
          ],
        }),
      }),
    );
  });
});

describe('PlanLineDecisionCell - a decided row', () => {
  const decided: PlanDecision = {
    buy: 182,
    stock: {
      qty: 6,
      sources: [
        { warehouse_id: 'wh-BRW-BB', warehouse_code: 'BRW-BB', qty: 5 },
        { warehouse_id: 'wh-PJ-SR', warehouse_code: 'PJ-SR', qty: 1 },
      ],
    },
  };

  it('reads in the past tense and stays short', () => {
    renderCell({ decision: decided });
    expect(screen.getByText('Stock 6 + Bought 182')).toBeInTheDocument();
    expect(screen.queryByText(/BRW-BB/)).not.toBeInTheDocument();
  });

  it('the breakdown is reachable without a mouse, and the truncated text keeps its tooltip', () => {
    renderCell({ decision: decided });
    const trigger = screen.getByRole('button', { name: 'Stock 6 + Bought 182' });
    expect(trigger).toHaveAttribute('title', 'Stock 6 + Bought 182');
  });

  it('a skip says so and offers no breakdown to hover', () => {
    renderCell({ decision: { skip: true } });
    expect(screen.getByText('Skipped')).toBeInTheDocument();
  });
});

describe('PlanLineDecisionCell - Adjust mixture goes through the shared helper', () => {
  it('scales the split down from the front when the buyer takes less than offered', () => {
    const l = line();
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    fireEvent.change(screen.getByLabelText('Units from stock'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));

    const next = onDecide.mock.calls.at(-1)![0] as PlanDecision;
    expect(next.stock).toEqual({
      qty: 2,
      sources: [expect.objectContaining({ warehouse_code: 'BRW-BB', qty: 2 })],
    });
  });

  it('never records more stock than the pool offered', () => {
    const l = line();
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    fireEvent.change(screen.getByLabelText('Units from stock'), { target: { value: '999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));

    expect((onDecide.mock.calls.at(-1)![0] as PlanDecision).stock?.qty).toBe(6);
  });
});

/**
 * A recorded buy is MoQ-legal wherever it was typed (review finding 1, round 2).
 *
 * The ledger rounded through `roundBuyQty` and these two paths did not, so the SAME row
 * recorded 14 from the Accept button and 20 from the ledger. The fixture is the one the
 * reviewer used: 20 needed, 10 order multiple, 6 covered from stock, so the raw remainder is
 * 14 and the only legal order is 20.
 */
describe('PlanLineDecisionCell - a recorded buy obeys MoQ and the order multiple', () => {
  const roundedLine = () =>
    line({ order_qty: 20, recommended_qty: 20, outstanding_sales: 20, order_multiple: 10 });

  it('accepting the suggestion records the rounded buy, never the raw remainder', () => {
    const l = roundedLine();
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Accept for SKU-1/ }));

    const next = onDecide.mock.calls.at(-1)![0] as PlanDecision;
    expect(next.buy).toBe(20);
    expect(next.stock?.qty).toBe(6);
  });

  it('the button states the figure it will record, so the label cannot lie', () => {
    const l = roundedLine();
    renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    expect(screen.getByRole('button', { name: /Accept for SKU-1/ })).toHaveTextContent(
      'Stock 6 + Buy 20',
    );
  });

  it('adjusting the mixture rounds the typed buy the same way', () => {
    const l = roundedLine();
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    fireEvent.change(screen.getByLabelText('Units to buy'), { target: { value: '14' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));

    expect((onDecide.mock.calls.at(-1)![0] as PlanDecision).buy).toBe(20);
  });

  it('a mixture that buys nothing records no buy at all, MoQ or not', () => {
    // A MoQ must not invent an order out of a row the buyer decided to cover outright.
    const l = line({ order_qty: 6, recommended_qty: 6, outstanding_sales: 6, moq: 100 });
    const { onDecide } = renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    fireEvent.click(screen.getByRole('button', { name: /Adjust the mix/i }));
    fireEvent.change(screen.getByLabelText('Units to buy'), { target: { value: '0' } });
    fireEvent.click(screen.getByRole('button', { name: 'Record' }));

    expect(onDecide.mock.calls.at(-1)![0]).not.toHaveProperty('buy');
  });
});

describe('PlanLineDecisionCell - the hover breakdown', () => {
  it('renders the parts as rows once the hover card opens', async () => {
    const l = line();
    renderCell({ line: l, cover: coverForLine(l, elsewhere) });

    const btn = screen.getByRole('button', { name: /Accept for SKU-1/ });
    fireEvent.pointerEnter(btn, { pointerType: 'mouse' });

    const card = await screen.findByText('Accept for SKU-1');
    const table = within(card.parentElement as HTMLElement).getByRole('table');
    expect(
      within(table)
        .getAllByRole('row')
        .map((r) => within(r).getAllByRole('cell').map((c) => c.textContent)),
    ).toEqual([
      ['BRW-BB', '5'],
      ['PJ-SR', '1'],
      ['Buy', '182'],
      ['Total', '188'],
    ]);
  });
});

/**
 * S16 (captain, 21 Aug, 3rd time requested): a GROUPED (product-grain) row's own read -
 * the unanimous decision its members agree on, or `mixed` when they do not. The cell never
 * computes this itself (that is `groupDecisionState`, `lib/planDecisions.ts`); `mixed` is
 * simply a prop it renders a notice for.
 */
describe('PlanLineDecisionCell - mixed (a grouped row whose members disagree)', () => {
  it('shows a mixed notice alongside the undecided controls, not in place of them', () => {
    const l = line({ order_qty: 1778, recommended_qty: 1778, outstanding_sales: 1778 });
    renderCell({ line: l, cover: coverForLine(l, []), mixed: true });

    expect(screen.getByText(/Mixed across locations/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Accept for SKU-1/ })).toBeInTheDocument();
  });

  it('is silent when not mixed, even though the row is still undecided', () => {
    const l = line({ order_qty: 1778, recommended_qty: 1778, outstanding_sales: 1778 });
    renderCell({ line: l, cover: coverForLine(l, []), mixed: false });

    expect(screen.queryByText(/Mixed across locations/)).not.toBeInTheDocument();
  });

  it('never shows the mixed notice once a DECIDED value is passed - a settled row is not mixed', () => {
    // A caller that somehow passes both `decision` and `mixed: true` gets the settled
    // (past-tense) row: `groupDecisionState` never actually produces this combination, but
    // the cell must not read `mixed` as an instruction to override a real decision.
    renderCell({ decision: { buy: 182 }, mixed: true });
    expect(screen.getByText('Bought 182')).toBeInTheDocument();
    expect(screen.queryByText(/Mixed across locations/)).not.toBeInTheDocument();
  });
});

/**
 * S16: `onDecide`/`onClear` write straight to the backend now (`usePlanLines.decide`/
 * `.clear`) and can reject. The cell owns the failure the same way `PlanMoqCell` owns its
 * own save - catch, and toast - so a rejected write never sits silent.
 */
describe('PlanLineDecisionCell - a rejected write toasts, the same pattern PlanMoqCell uses', () => {
  beforeEach(() => vi.mocked(toast.error).mockClear());

  it('Accept: a rejected onDecide toasts the error message', async () => {
    const onDecide = vi.fn().mockRejectedValue(new Error('Failed to record the decision.'));
    const l = line({ order_qty: 1778, recommended_qty: 1778, outstanding_sales: 1778 });
    renderCell({ line: l, cover: coverForLine(l, []), onDecide });

    fireEvent.click(screen.getByRole('button', { name: /Accept for SKU-1/ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to record the decision.'),
    );
  });

  it('Accept: a rejection with no message falls back to a generic sentence', async () => {
    const onDecide = vi.fn().mockRejectedValue('not an Error');
    const l = line({ order_qty: 1778, recommended_qty: 1778, outstanding_sales: 1778 });
    renderCell({ line: l, cover: coverForLine(l, []), onDecide });

    fireEvent.click(screen.getByRole('button', { name: /Accept for SKU-1/ }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Could not record the decision.'),
    );
  });

  it('Skip: a rejected onDecide toasts too', async () => {
    const onDecide = vi.fn().mockRejectedValue(new Error('Network error.'));
    renderCell({ onDecide });

    fireEvent.click(screen.getByRole('button', { name: /Skip SKU-1/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Network error.'));
  });

  it('Change (clear): a rejected onClear toasts its own message', async () => {
    const onClear = vi.fn().mockRejectedValue(new Error('Failed to clear the decision.'));
    renderCell({ decision: { buy: 182 }, onClear });

    fireEvent.click(screen.getByRole('button', { name: /Change/i }));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Failed to clear the decision.'),
    );
  });

  it('a successful write never toasts', async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined);
    renderCell({ onDecide });

    fireEvent.click(screen.getByRole('button', { name: /Skip SKU-1/i }));

    await waitFor(() => expect(onDecide).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });
});
