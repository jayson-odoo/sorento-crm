/**
 * SCM M8 - CashCopilotResults (slice C). The funded/deferred experience as ONE
 * table (two draggable sections) with the budget control in the funded header,
 * the needs-cost banner, and the confirm-decisions bar.
 *   M8-C1 two sections · M8-C2 clearable budget input · M8-C7 needs-cost banner
 *   M8-C8 confirm bar → confirm decisions
 *
 * Driven by a fabricated `M8PlanState` (the hook is unit-tested separately in
 * useReorderPlan.test.tsx). Wrapped in a QueryClientProvider because the reused
 * detail dialog mounts react-query hooks lazily.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReorderRecommendation } from '../types/reorder.types';
import { recToPlanRow, type M8PlanRow } from '../lib/planRow';
import type { M8PlanState } from '../hooks/useReorderPlan';

class ResizeObserverStub { observe() {} unobserve() {} disconnect() {} }
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

const toastSuccess = vi.fn();
const toastError = vi.fn();
const toastInfo = vi.fn();
vi.mock('sonner', () => ({
  toast: { success: (...a: unknown[]) => toastSuccess(...a), error: (...a: unknown[]) => toastError(...a), info: (...a: unknown[]) => toastInfo(...a) },
}));

import { CashCopilotResults } from './CashCopilotResults';

function rec(id: string, over: Partial<ReorderRecommendation> = {}): ReorderRecommendation {
  return {
    id, type: 'buy', sku: `SKU-${id}`, product_name: `Product ${id}`,
    abc_class: 'A', xyz_class: 'X', warehouse_code: 'WH-KL', warehouse_name: 'Kuala Lumpur DC',
    product_id: `prod-${id}`, warehouse_id: 'wh-1', is_network: false, allocation: null,
    order_qty: 10, recommended_qty: 10, reorder_point: 5, min_qty: null, max_qty: null,
    order_up_to: 20, net_position: 3, days_of_cover: 6, reason: 'reorder_point',
    reason_label: 'net ≤ ROP', confidence: 'high', sample_size: 40,
    supplier: { supplier_code: 'SUP-ACME', supplier_name: 'Acme', unit_cost: 100, lead_time_days: 14, composite_score: 88, is_primary: true },
    alternatives: [], is_exception: false, disposition_action: null, transfer_flag: null,
    forecast_daily_demand: 1, lead_time_days: 14, lead_time_source: 'measured', safety_stock: 2,
    safety_stock_method: 'fixed_days', safety_stock_fallback: null, service_level: 0.95, safety_days: 7,
    review_days: 30, moq: 1, order_multiple: 1, policy_type: 'reorder_point', supplier_selection: 'primary',
    unit_cost: 100, cash_impact: 1000, rank: 1, rank_score: 0.9, funding_status: null,
    days_to_stockout: 6, rank_factors: [], ...over,
  };
}

/** Fabricate the plan-state contract CashCopilotResults consumes. */
function makePlan(over: Partial<M8PlanState> = {}): { plan: M8PlanState; setBudget: ReturnType<typeof vi.fn>; confirm: ReturnType<typeof vi.fn> } {
  const within: M8PlanRow[] = [recToPlanRow(rec('a'))];
  const over_: M8PlanRow[] = [recToPlanRow(rec('b', { rank: 2 }))];
  const needsCost: M8PlanRow[] = over.funding?.needsCost ?? [];
  const setBudget = vi.fn();
  const confirm = vi.fn().mockResolvedValue({ confirmed_count: 1, po_count: 1 });
  const plan = {
    runId: 'run-1',
    rows: [...within, ...over_],
    budget: 5000,
    setBudget,
    pins: new Set<string>(),
    rejects: new Set<string>(),
    editedIds: new Set<string>(),
    funding: { within, over: over_, needsCost, committed: 1000, free: 4000 },
    decisions: { a: null, b: null },
    decisionsById: {},
    poByRow: {},
    fund: vi.fn(),
    defer: vi.fn(),
    reject: vi.fn(),
    editRow: vi.fn(),
    applyProposalLine: vi.fn(),
    confirm,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isConfirming: false,
    ...over,
  } as unknown as M8PlanState;
  return { plan, setBudget, confirm };
}

function renderCopilot(planBundle: ReturnType<typeof makePlan>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CashCopilotResults plan={planBundle.plan} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  toastSuccess.mockReset();
  toastError.mockReset();
  toastInfo.mockReset();
});

describe('CashCopilotResults - one table, two sections (M8-C1)', () => {
  it('renders the Within-budget and Over-budget sections with their rows', () => {
    renderCopilot(makePlan());
    expect(screen.getByText('Within budget')).toBeInTheDocument();
    expect(screen.getByText('Over budget')).toBeInTheDocument();
    expect(screen.getByText('SKU-a')).toBeInTheDocument();
    expect(screen.getByText('SKU-b')).toBeInTheDocument();
  });
});

describe('CashCopilotResults - clearable budget input (M8-C2)', () => {
  it('drives setBudget on change and treats an emptied input as 0 (no stuck leading 0)', () => {
    const bundle = makePlan();
    renderCopilot(bundle);
    const input = screen.getByLabelText('Cash budget') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '7000' } });
    expect(bundle.setBudget).toHaveBeenLastCalledWith(7000);
    // fully clearable → empty is 0 for the split, and the field shows blank (not "0")
    fireEvent.change(input, { target: { value: '' } });
    expect(bundle.setBudget).toHaveBeenLastCalledWith(0);
    expect(input.value).toBe('');
  });
});

describe('CashCopilotResults - the buys nothing can price', () => {
  // A missing price is a gap in our master data, not a reason the shortage went away.
  // These rows have to be visible and orderable, or the buyer never learns the item is
  // short and never fulfils it. They stay out of the budget arithmetic only.
  it('lists an unpriced buy in its own section, not as a dismissible note', () => {
    const bundle = makePlan({
      funding: {
        within: [recToPlanRow(rec('a'))],
        over: [],
        needsCost: [
          recToPlanRow(rec('x', { unit_cost: null, cash_impact: null, supplier: null })),
        ],
        committed: 1000,
        free: 4000,
      },
    } as Partial<M8PlanState>);
    renderCopilot(bundle);
    expect(screen.getByText('No price yet')).toBeInTheDocument();
    // The row itself is on screen, with its reason, so it can be accepted and ordered.
    expect(screen.getByText('SKU-x')).toBeInTheDocument();
    expect(screen.getByText('No cost')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Add a cost/i })).toBeInTheDocument();
  });

  it('states the section is empty rather than hiding it when every buy has a price', () => {
    renderCopilot(makePlan());
    expect(screen.getByText('No price yet')).toBeInTheDocument();
    expect(screen.getByText(/Every buy in this plan has a price/i)).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Add a cost/i })).not.toBeInTheDocument();
  });
});

describe('CashCopilotResults - confirm decisions (M8-C8 / M8-F2)', () => {
  it('hides the confirm bar when within-budget rows exist but NO decision is accepted (M8-F2)', () => {
    // default plan: SKU-a is within budget, but no accept/adjust decision is staged.
    // The bar must NOT show merely because a fundable row exists.
    renderCopilot(makePlan());
    expect(screen.queryByText(/ready to confirm into draft purchase orders/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm decisions/i })).not.toBeInTheDocument();
  });

  it('surfaces the confirm bar only once a line is accepted, and confirms into draft POs', async () => {
    // M8-F2: the bar is gated on an ACCEPTED/adjusted decision, not merely on
    // within-budget rows existing. Seed one accepted decision so the bar shows.
    const bundle = makePlan({ decisions: { a: 'accepted', b: null } } as Partial<M8PlanState>);
    renderCopilot(bundle);
    // the confirm bar counts the accepted lines ready to materialise
    expect(screen.getByText(/ready to confirm into draft purchase orders/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Confirm decisions/i }));
    // the confirm dialog opens; confirming runs plan.confirm()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm decisions' }));
    await waitFor(() => expect(bundle.confirm).toHaveBeenCalled());
    await waitFor(() => expect(toastSuccess).toHaveBeenCalled());
  });

  it('hides the confirm bar once every accepted line already has a draft PO (M8-F9)', () => {
    // An accepted line that has already been materialised into a draft PO is no
    // longer "pending confirmation" - with only that line accepted, the bar hides.
    const bundle = makePlan({
      decisions: { a: 'accepted', b: null },
      poByRow: { a: { po_number: 'PO-2026-0007', po_id: 'po-abc' } },
    } as Partial<M8PlanState>);
    renderCopilot(bundle);
    expect(screen.queryByText(/ready to confirm into draft purchase orders/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Confirm decisions/i })).not.toBeInTheDocument();
  });
});
