/**
 * Stage 1B and 1C - the list, reconciliation, supply and confirmation hooks.
 *
 * What is worth pinning here is the wiring, not the rendering: the reconciliation and the
 * supply are both off until there is an order to ask about and its sheet is open, a rerun
 * invalidates every surface that carries the review state (the planning worklist, the
 * reconciliation itself, the project's SO list, and the SO detail header), and a
 * confirmation invalidates those plus the supply and the ORDER INQUIRY - the confirmed Buy
 * residual is what purchasing is handed, so a stale inquiry list is the one place the
 * decision would look like it had not happened.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  ConfirmSupplyBody,
  ReconciliationSummary,
  SupplyProposal,
} from '../types/fulfilmentPlanning.types';

const listFulfilmentPlanning = vi.fn();
const getReconciliation = vi.fn();
const rerunReconciliation = vi.fn();
const getSupply = vi.fn();
const confirmSupply = vi.fn();
const getStockDetail = vi.fn();

vi.mock('../services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: (...args: unknown[]) => listFulfilmentPlanning(...args),
  getReconciliation: (...args: unknown[]) => getReconciliation(...args),
  rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
  getSupply: (...args: unknown[]) => getSupply(...args),
  confirmSupply: (...args: unknown[]) => confirmSupply(...args),
  getStockDetail: (...args: unknown[]) => getStockDetail(...args),
}));

const toastSuccess = vi.fn();
const toastWarning = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    warning: (...args: unknown[]) => toastWarning(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

import {
  FULFILMENT_PLANNING_KEY,
  PILE_QUEUE_KEY,
  RECONCILIATION_KEY,
  STOCK_DETAIL_KEY,
  SUPPLY_KEY,
  useFulfilmentPlanning,
  useReconciliation,
  useReconciliationMutations,
  useStockDetail,
  useSupply,
} from './useFulfilmentPlanning';
import {
  ORDER_INQUIRY_ROWS_KEY,
  ORDER_INQUIRY_SUMMARY_KEY,
  ORDER_INQUIRY_WORKLIST_KEY,
  ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
} from './useOrderInquiry';
import { SALES_ORDERS_KEY, SALES_ORDER_KEY } from './useProjectSalesOrders';

function summary(overrides: Partial<ReconciliationSummary> = {}): ReconciliationSummary {
  return {
    project_sales_order_id: 'pso-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: 'proj-1',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    customer_name: 'Buimaco Sdn Bhd (Project)',
    po_number: 'HQ/26/01/121',
    area_group: 'TOWER',
    status: 'published',
    review_state: 'needs_cs_review',
    header: { outcome: 'linked', core_so_number: 'SO376201', reason: 'Linked.' },
    lines: [],
    exceptions: [],
    lines_total: 0,
    lines_linked: 0,
    ...overrides,
  };
}

function supplyProposal(overrides: Partial<SupplyProposal> = {}): SupplyProposal {
  return {
    project_sales_order_id: 'pso-1',
    provisional_ref: 'PSO-000123',
    autocount_doc_no: 'SO376201',
    project_id: 'proj-1',
    project_code: 'PRJ-0041',
    project_name: 'Tuju Residences',
    status: 'published',
    review_state: 'needs_cs_review',
    lines: [],
    ...overrides,
  };
}

const CONFIRM_BODY: ConfirmSupplyBody = {
  lines: [
    {
      project_line_id: 'pl-1',
      timely_spo_qty: '0',
      reserve: [],
      borrow: [],
      buy_qty: '600',
      buy_reason: null,
    },
  ],
};

let client: QueryClient;
let invalidated: unknown[][];

function wrapper() {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryWrapper';
  return Wrapper;
}

beforeEach(() => {
  vi.clearAllMocks();
  invalidated = [];
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  const original = client.invalidateQueries.bind(client);
  client.invalidateQueries = ((filters?: { queryKey?: unknown[] }) => {
    if (filters?.queryKey) invalidated.push(filters.queryKey);
    return original(filters as never);
  }) as typeof client.invalidateQueries;
});

describe('useFulfilmentPlanning', () => {
  it('lists with the params it is given', async () => {
    listFulfilmentPlanning.mockResolvedValue({ data: [], total: 0, page: 1, limit: 25 });

    const { result } = renderHook(
      () => useFulfilmentPlanning({ page: 1, limit: 25, review_state: 'needs_cs_review' }),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(listFulfilmentPlanning).toHaveBeenCalledTimes(1));
    expect(listFulfilmentPlanning).toHaveBeenCalledWith({
      page: 1,
      limit: 25,
      review_state: 'needs_cs_review',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useReconciliation', () => {
  it('reads the reconciliation once an id is given', async () => {
    getReconciliation.mockResolvedValue(summary());

    const { result } = renderHook(() => useReconciliation('pso-1'), { wrapper: wrapper() });

    await waitFor(() => expect(getReconciliation).toHaveBeenCalledWith('pso-1'));
    await waitFor(() => expect(result.current.data?.review_state).toBe('needs_cs_review'));
  });

  it('asks nothing while there is no order to open', () => {
    renderHook(() => useReconciliation(undefined), { wrapper: wrapper() });

    expect(getReconciliation).not.toHaveBeenCalled();
  });

  it('asks nothing while the sheet is closed, even with an id in hand', () => {
    renderHook(() => useReconciliation('pso-1', false), { wrapper: wrapper() });

    expect(getReconciliation).not.toHaveBeenCalled();
  });
});

describe('useSupply', () => {
  it('reads the composition once an id is given', async () => {
    getSupply.mockResolvedValue(supplyProposal());

    const { result } = renderHook(() => useSupply('pso-1'), { wrapper: wrapper() });

    await waitFor(() => expect(getSupply).toHaveBeenCalledWith('pso-1'));
    await waitFor(() => expect(result.current.data?.provisional_ref).toBe('PSO-000123'));
  });

  it('asks nothing while there is no order to open', () => {
    renderHook(() => useSupply(undefined), { wrapper: wrapper() });

    expect(getSupply).not.toHaveBeenCalled();
  });

  it('asks nothing while the sheet is closed: it reads live stock per line', () => {
    renderHook(() => useSupply('pso-1', false), { wrapper: wrapper() });

    expect(getSupply).not.toHaveBeenCalled();
  });

  it('refetches the pill sources when the composition disagrees about the review state', async () => {
    // An out-of-band change flips the decision to challenged; only the supply read
    // notices, so a cached "Confirmed" reconciliation must be refetched, not trusted.
    // Both hooks render, as they do in the open sheet, so the reconciliation data is
    // held by an observer rather than collected by gcTime: 0.
    getReconciliation.mockResolvedValue(summary({ review_state: 'confirmed' }));
    getSupply.mockResolvedValue(supplyProposal({ review_state: 'needs_cs_review' }));

    renderHook(
      () => {
        useReconciliation('pso-1');
        return useSupply('pso-1');
      },
      { wrapper: wrapper() },
    );

    await waitFor(() =>
      expect(invalidated).toEqual(
        expect.arrayContaining([[RECONCILIATION_KEY, 'pso-1'], [FULFILMENT_PLANNING_KEY]]),
      ),
    );
  });

  it('leaves the caches alone when both sources agree', async () => {
    getReconciliation.mockResolvedValue(summary({ review_state: 'needs_cs_review' }));
    getSupply.mockResolvedValue(supplyProposal({ review_state: 'needs_cs_review' }));

    const { result } = renderHook(
      () => {
        useReconciliation('pso-1');
        return useSupply('pso-1');
      },
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(invalidated).toEqual([]);
  });
});

describe('useReconciliationMutations', () => {
  async function rerunOn(psoId: string) {
    let mutations: ReturnType<typeof useReconciliationMutations> | null = null;
    function Harness({ onReady }: { onReady: (api: typeof mutations) => void }) {
      const api = useReconciliationMutations();
      React.useEffect(() => {
        onReady(api);
      }, [api, onReady]);
      return null;
    }
    render(
      <QueryClientProvider client={client}>
        <Harness onReady={(value) => (mutations = value)} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(mutations).not.toBeNull());
    await mutations!.rerun.mutateAsync(psoId);
    return mutations!;
  }

  it('invalidates the planning list, the reconciliation, and both sales-order surfaces', async () => {
    rerunReconciliation.mockResolvedValue(summary({ exceptions: [] }));

    await rerunOn('pso-1');

    const flattened = invalidated.map((key) => JSON.stringify(key));
    expect(flattened.some((key) => key.includes(FULFILMENT_PLANNING_KEY))).toBe(true);
    expect(flattened.some((key) => key.includes(RECONCILIATION_KEY))).toBe(true);
    expect(flattened.some((key) => key.includes(SALES_ORDERS_KEY))).toBe(true);
    expect(flattened.some((key) => key.includes(SALES_ORDER_KEY))).toBe(true);
  });

  it('celebrates a clean rerun', async () => {
    rerunReconciliation.mockResolvedValue(summary({ exceptions: [] }));

    await rerunOn('pso-1');

    expect(toastSuccess).toHaveBeenCalledWith(
      'Reconciled. This sales order is ready for CS review.',
    );
    expect(toastWarning).not.toHaveBeenCalled();
  });

  it('names how many exceptions are still open, pluralized', async () => {
    rerunReconciliation.mockResolvedValue(
      summary({
        exceptions: [
          { kind: 'missing', line_no: 2, item_code: 'SRT501-CP', message: 'No AutoCount line.' },
          { kind: 'surplus', item_code: 'SRT770-BK', message: 'Spare on AutoCount.' },
        ],
      }),
    );

    await rerunOn('pso-1');

    expect(toastWarning).toHaveBeenCalledWith('2 exceptions still to clear on this sales order.');
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('reports a failed rerun instead of a silent no-op', async () => {
    rerunReconciliation.mockRejectedValue(new Error('That order was rebuilt'));

    await expect(rerunOn('pso-1')).rejects.toThrow('That order was rebuilt');

    expect(toastError).toHaveBeenCalledWith('That order was rebuilt');
    expect(toastSuccess).not.toHaveBeenCalled();
    expect(toastWarning).not.toHaveBeenCalled();
  });

  // ------------------------------------------------------- the confirmation
  async function confirmOn(psoId: string, body: ConfirmSupplyBody = CONFIRM_BODY) {
    let mutations: ReturnType<typeof useReconciliationMutations> | null = null;
    function Harness({ onReady }: { onReady: (api: typeof mutations) => void }) {
      const api = useReconciliationMutations();
      React.useEffect(() => {
        onReady(api);
      }, [api, onReady]);
      return null;
    }
    render(
      <QueryClientProvider client={client}>
        <Harness onReady={(value) => (mutations = value)} />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(mutations).not.toBeNull());
    await mutations!.confirm.mutateAsync({ psoId, body });
    return mutations!;
  }

  it('sends the whole order in one call', async () => {
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    await confirmOn('pso-1');

    expect(confirmSupply).toHaveBeenCalledTimes(1);
    expect(confirmSupply).toHaveBeenCalledWith('pso-1', CONFIRM_BODY);
  });

  it('invalidates every key family the decision shows up in, order inquiry included', async () => {
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    await confirmOn('pso-1');

    const flattened = invalidated.map((key) => JSON.stringify(key));
    for (const key of [
      FULFILMENT_PLANNING_KEY,
      RECONCILIATION_KEY,
      SUPPLY_KEY,
      SALES_ORDERS_KEY,
      SALES_ORDER_KEY,
      ORDER_INQUIRY_ROWS_KEY,
      ORDER_INQUIRY_SUMMARY_KEY,
      ORDER_INQUIRY_WORKLIST_KEY,
      ORDER_INQUIRY_WORKLIST_SUMMARY_KEY,
      PILE_QUEUE_KEY,
      STOCK_DETAIL_KEY,
    ]) {
      expect(flattened.some((entry) => entry.includes(key))).toBe(true);
    }
  });

  it('names the revision and how many purchase rows were handed over', async () => {
    confirmSupply.mockResolvedValue({
      revision_no: 3,
      confirmed_at: '2026-08-18T02:00:00',
      review_state: 'confirmed',
      inquiry_rows_created: 2,
      exceptions: [],
    });

    await confirmOn('pso-1');

    expect(toastSuccess).toHaveBeenCalledWith(
      'Confirmed as revision 3. 2 purchase rows handed over.',
    );
  });

  it('says "1 purchase row" rather than "1 purchase rows"', async () => {
    confirmSupply.mockResolvedValue({
      revision_no: 1,
      confirmed_at: '2026-08-18T02:00:00',
      review_state: 'confirmed',
      inquiry_rows_created: 1,
      exceptions: [],
    });

    await confirmOn('pso-1');

    expect(toastSuccess).toHaveBeenCalledWith(
      'Confirmed as revision 1. 1 purchase row handed over.',
    );
  });

  it('reports a refusal in one short sentence: the failing lines belong on the sheet', async () => {
    confirmSupply.mockRejectedValue(new Error('This sales order could not be confirmed'));

    await expect(confirmOn('pso-1')).rejects.toThrow(
      'This sales order could not be confirmed',
    );

    expect(toastError).toHaveBeenCalledWith('This sales order could not be confirmed');
    expect(toastSuccess).not.toHaveBeenCalled();
    // Nothing is invalidated by a refusal: nothing was written.
    expect(invalidated).toEqual([]);
  });
});

describe('useStockDetail', () => {
  it('reads the detail by ids under the exported key, so a confirmation can invalidate it', async () => {
    getStockDetail.mockResolvedValue({ product_id: 'prod-1', warehouse_id: 'wh-1' });

    const { result } = renderHook(() => useStockDetail('prod-1', 'wh-1'), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(getStockDetail).toHaveBeenCalledWith('prod-1', 'wh-1'));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(client.getQueryData([STOCK_DETAIL_KEY, 'prod-1', 'wh-1'])).toEqual({
      product_id: 'prod-1',
      warehouse_id: 'wh-1',
    });
  });
});
