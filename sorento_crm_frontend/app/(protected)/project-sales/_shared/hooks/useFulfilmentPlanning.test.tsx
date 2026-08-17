/**
 * Stage 1B - the list, reconciliation and rerun hooks.
 *
 * What is worth pinning here is the wiring, not the rendering: the reconciliation query is
 * off until there is an order to ask about, and a rerun invalidates every surface that
 * carries the review state (the planning worklist, the reconciliation itself, the project's
 * SO list, and the SO detail header) so none of them is left showing a cleared exception as
 * still open.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReconciliationSummary } from '../types/fulfilmentPlanning.types';

const listFulfilmentPlanning = vi.fn();
const getReconciliation = vi.fn();
const rerunReconciliation = vi.fn();

vi.mock('../services/fulfilmentPlanningService', () => ({
  listFulfilmentPlanning: (...args: unknown[]) => listFulfilmentPlanning(...args),
  getReconciliation: (...args: unknown[]) => getReconciliation(...args),
  rerunReconciliation: (...args: unknown[]) => rerunReconciliation(...args),
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
  RECONCILIATION_KEY,
  useFulfilmentPlanning,
  useReconciliation,
  useReconciliationMutations,
} from './useFulfilmentPlanning';
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
});
