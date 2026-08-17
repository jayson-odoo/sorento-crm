/**
 * S7b - the loading plan screen.
 *
 * What is asserted is the part a user would be misled by if it broke: a deferred line is
 * visible WITH its reason (the screen exists to answer "why is my line not on it"), an empty
 * stock list names the upload rather than showing an empty table, and changing the container
 * count re-runs the same plan instead of creating a second one.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  });
}
if (!window.ResizeObserver) {
  (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const state = {
  suppliers: [{ value: 'sup-1', label: 'Foshan Ceramics' }],
  sizes: [{ code: '40HQ', label: '40ft high cube', cbm: 68, is_default: true }],
  stock: { supplier_id: 'sup-1', as_of: '2026-07-31', rows: [] as unknown[] },
  unfinished: [] as unknown[],
  plans: [] as unknown[],
};

const build = vi.fn();
const rerun = vi.fn();

vi.mock('../../hooks/useFulfilment', () => ({
  useFulfilmentSuppliers: () => ({ data: state.suppliers, isLoading: false }),
  useContainerSizes: () => ({ data: state.sizes, isLoading: false }),
  useSupplierStock: () => ({ data: state.stock, isLoading: false }),
  useUnfinishedStock: () => ({ data: state.unfinished, isLoading: false }),
  useLoadingPlans: () => ({ data: state.plans, isLoading: false }),
  useBuildLoadingPlan: () => ({ mutate: build, isPending: false, data: buildResult }),
  useRerunLoadingPlan: () => ({ mutate: rerun, isPending: false, data: rerunResult }),
  useStockListApplied: () => vi.fn(),
  useDeleteLoadingPlan: () => ({ mutate: vi.fn(), isPending: false }),
  // S8's panel renders inside this view. Its own behaviour is covered in
  // SupplierNoticePanel.test.tsx; here it only has to not explode.
  usePlanNotices: () => ({ data: [], isLoading: false }),
  useApproveLoadingPlan: () => ({ mutate: vi.fn(), isPending: false }),
}));

let buildResult: unknown = undefined;
let rerunResult: unknown = undefined;

import { LoadingPlanView } from './LoadingPlanView';

function plan(over: Record<string, unknown> = {}) {
  return {
    id: 'plan-1',
    supplier_id: 'sup-1',
    supplier_name: 'Foshan Ceramics',
    container_type: '40HQ',
    container_count: 1,
    container_cbm: 68,
    capacity_cbm: 68,
    planned_cbm: 34,
    fill_rate: 0.5,
    line_count: 2,
    deferred_count: 1,
    unmeasured_count: 0,
    inventory_as_of: '2026-07-31',
    computed_at: '2026-08-05T00:00:00',
    created_by: null,
    lines: [
      {
        id: 'l1',
        po_line_id: 'pol-1',
        po_number: 'PO-0001',
        item_code: 'SRTWC8613',
        qty_outstanding: 100,
        qty_packed_available: 100,
        qty_planned: 100,
        cbm_per_unit: 0.34,
        cbm_planned: 34,
        volume_basis: 'supplier',
        rank: 1,
        rank_score: 1,
        factors: [
          { key: 'po_document_sequence', weight: 1, value: 1, present: true },
          { key: 'need_by_date', weight: 0, value: null, present: false },
        ],
        status: 'allocated',
        deferral_reason: null,
      },
      {
        id: 'l2',
        po_line_id: 'pol-2',
        po_number: 'PO-0002',
        item_code: 'SRTWB1001',
        qty_outstanding: 200,
        qty_packed_available: 0,
        qty_planned: 0,
        cbm_per_unit: 0.5,
        cbm_planned: 0,
        volume_basis: 'supplier',
        rank: 2,
        rank_score: 0,
        factors: [],
        status: 'deferred',
        deferral_reason: 'no_packed_stock',
      },
    ],
    ...over,
  };
}

function renderView() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LoadingPlanView />
    </QueryClientProvider>,
  );
}

/** The supplier select is a combobox; pick the only option in it. */
async function chooseSupplier() {
  const trigger = screen.getByRole('combobox', { name: /Supplier/i });
  fireEvent.pointerDown(trigger, { button: 0, ctrlKey: false });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByText('Foshan Ceramics'));
}

beforeEach(() => {
  build.mockReset();
  rerun.mockReset();
  buildResult = undefined;
  rerunResult = undefined;
  state.stock = { supplier_id: 'sup-1', as_of: '2026-07-31', rows: [] };
  state.unfinished = [];
  state.plans = [];
});

describe('LoadingPlanView - before a supplier is chosen', () => {
  it('says what to do rather than showing an empty plan', async () => {
    renderView();

    expect(await screen.findByText('Choose a supplier to plan a container.')).toBeInTheDocument();
  });
});

describe('LoadingPlanView - a supplier with no stock list', () => {
  it('names the upload that fills the screen', async () => {
    renderView();
    await chooseSupplier();

    expect(await screen.findByText(/No stock list for Foshan Ceramics yet/)).toBeInTheDocument();
  });
});

describe('LoadingPlanView - the plan', () => {
  beforeEach(() => {
    state.stock = {
      supplier_id: 'sup-1',
      as_of: '2026-07-31',
      rows: [
        {
          item_code: 'SRTWC8613',
          product_id: 'p1',
          product_name: 'Toilet',
          qty_packed: 100,
          qty_unfinished: 40,
          cbm_per_unit: 0.34,
          matched: true,
        },
      ],
    };
  });

  it('shows what the supplier holds and when they said so', async () => {
    renderView();
    await chooseSupplier();

    expect(await screen.findByText(/As they told us on/)).toBeInTheDocument();
    expect(screen.getByText('Items packed')).toBeInTheDocument();
  });

  it('shows a deferred line with the reason it was cut', async () => {
    // The whole point of the screen: "why is my line not on the container".
    buildResult = plan();
    renderView();
    await chooseSupplier();

    expect(await screen.findByText('SRTWB1001')).toBeInTheDocument();
    expect(screen.getByText('Not packed yet')).toBeInTheDocument();
    expect(screen.getByText('Not loaded')).toBeInTheDocument();
  });

  it('states the fill against the capacity, not just the planned volume', async () => {
    buildResult = plan();
    renderView();
    await chooseSupplier();

    expect(await screen.findByText('68 cbm')).toBeInTheDocument();
    expect(screen.getByText('50% full')).toBeInTheDocument();
  });

  it('keeps a volume to three decimals, which is how a cbm is quoted', async () => {
    // Container and item volumes are 3 dp in this trade (a pan is 0.123 cbm, not 0.12).
    // Rounding to 2 loses a real difference between two products.
    buildResult = plan({ capacity_cbm: 68.125, planned_cbm: 34.5 });
    renderView();
    await chooseSupplier();

    expect(await screen.findByText('68.125 cbm')).toBeInTheDocument();
  });

  it('changing the container count re-runs the same plan rather than making another', async () => {
    // AC-E6. `rerun` carries the plan id; `build` would create a second plan for one decision.
    buildResult = plan();
    renderView();
    await chooseSupplier();
    await screen.findByText('SRTWC8613');

    fireEvent.change(screen.getByLabelText('How many'), { target: { value: '2' } });

    await waitFor(() => expect(rerun).toHaveBeenCalledWith({ id: 'plan-1', container_count: 2 }));
    expect(build).not.toHaveBeenCalled();
  });

  it('builds a plan for the chosen supplier and container', async () => {
    renderView();
    await chooseSupplier();

    fireEvent.click(await screen.findByRole('button', { name: /Plan containers/ }));

    await waitFor(() =>
      expect(build).toHaveBeenCalledWith({
        supplier_id: 'sup-1',
        container_count: 1,
        container_type: '40HQ',
      }),
    );
  });

  it('lists unfinished stock separately from the plan', async () => {
    // AC-E2: it is a production request, not freight, and mixing them is how somebody loads
    // a container with things that do not exist.
    state.unfinished = [
      { item_code: 'SRTWC8613', product_name: 'Toilet', qty_unfinished: 140, qty_packed: 2, as_of: '2026-07-31' },
    ];
    renderView();
    await chooseSupplier();

    expect(await screen.findByText('Waiting on production')).toBeInTheDocument();
    expect(screen.getByText('140')).toBeInTheDocument();
  });
});
