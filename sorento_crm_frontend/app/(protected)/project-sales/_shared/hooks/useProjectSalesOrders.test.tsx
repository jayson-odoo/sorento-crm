/**
 * A save on the sales-order detail page must refresh every query that page reads.
 *
 * The allocation panel sits on the same page and reads its own key. Pinned on the invalidated
 * KEYS rather than rendered output, because the failure is a cache-wiring mistake: the save
 * would answer 200 and the panel would keep describing the lines from before it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const saveSalesOrderDocument = vi.fn();
const unpublishSalesOrder = vi.fn();
const bulkSetLinesStockLocation = vi.fn();

vi.mock('../services/projectSalesOrderService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectSalesOrderService')>();
  return {
    ...actual,
    saveSalesOrderDocument: (...args: unknown[]) => saveSalesOrderDocument(...args),
    unpublishSalesOrder: (...args: unknown[]) => unpublishSalesOrder(...args),
    bulkSetLinesStockLocation: (...args: unknown[]) => bulkSetLinesStockLocation(...args),
  };
});

const toast = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}));
vi.mock('sonner', () => ({ toast }));

import {
  SALES_ORDERS_KEY,
  salesOrderKey,
  useBulkSetLinesStockLocation,
  useSalesOrderMutations,
} from './useProjectSalesOrders';
import { allocationsKey } from './useProjectAllocations';

const PROJECT_ID = 'proj-1';
const PSO_ID = 'pso-1';

function Harness({ onReady }: { onReady: (api: ReturnType<typeof useSalesOrderMutations>) => void }) {
  const api = useSalesOrderMutations(PROJECT_ID, PSO_ID);
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

let client: QueryClient;
let invalidated: unknown[][];

beforeEach(() => {
  vi.clearAllMocks();
  invalidated = [];
  client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const original = client.invalidateQueries.bind(client);
  client.invalidateQueries = ((filters?: { queryKey?: unknown[] }) => {
    if (filters?.queryKey) invalidated.push(filters.queryKey);
    return original(filters as never);
  }) as typeof client.invalidateQueries;
});

async function saveTheDocument() {
  let api: ReturnType<typeof useSalesOrderMutations> | null = null;
  render(
    <QueryClientProvider client={client}>
      <Harness onReady={(value) => (api = value)} />
    </QueryClientProvider>,
  );
  await act(async () => {
    await api!.save.mutateAsync({ lines: [] } as never);
  });
}

describe('useSalesOrderMutations.save', () => {
  it('refreshes the order, the project list and the allocations the same page shows', async () => {
    saveSalesOrderDocument.mockResolvedValue({ data: { id: PSO_ID } });

    await saveTheDocument();

    expect(saveSalesOrderDocument).toHaveBeenCalledWith(PSO_ID, { lines: [] });
    expect(invalidated).toEqual(
      expect.arrayContaining([
        salesOrderKey(PSO_ID),
        [SALES_ORDERS_KEY, PROJECT_ID],
        allocationsKey(PSO_ID),
      ]),
    );
  });
});

describe('useSalesOrderMutations.unpublish', () => {
  it('refreshes the order and the project list, and toasts on success', async () => {
    unpublishSalesOrder.mockResolvedValue({ status: 'draft', provisional_ref: 'PSO-000001' });
    let api: ReturnType<typeof useSalesOrderMutations> | null = null;
    render(
      <QueryClientProvider client={client}>
        <Harness onReady={(value) => (api = value)} />
      </QueryClientProvider>,
    );

    await act(async () => {
      await api!.unpublish.mutateAsync();
    });

    expect(unpublishSalesOrder).toHaveBeenCalledWith(PSO_ID);
    expect(invalidated).toEqual(
      expect.arrayContaining([salesOrderKey(PSO_ID), [SALES_ORDERS_KEY, PROJECT_ID]]),
    );
    expect(toast.success).toHaveBeenCalledWith('Sales order returned to draft');
  });

  it('toasts the server refusal rather than silently doing nothing', async () => {
    unpublishSalesOrder.mockRejectedValue(new Error('carries a published amendment'));
    let api: ReturnType<typeof useSalesOrderMutations> | null = null;
    render(
      <QueryClientProvider client={client}>
        <Harness onReady={(value) => (api = value)} />
      </QueryClientProvider>,
    );

    await act(async () => {
      await expect(api!.unpublish.mutateAsync()).rejects.toThrow();
    });

    expect(toast.error).toHaveBeenCalledWith('carries a published amendment');
  });
});

function BulkHarness({
  onReady,
}: {
  onReady: (api: ReturnType<typeof useBulkSetLinesStockLocation>) => void;
}) {
  const api = useBulkSetLinesStockLocation(PROJECT_ID, PSO_ID);
  React.useEffect(() => {
    onReady(api);
  }, [api, onReady]);
  return null;
}

describe('useBulkSetLinesStockLocation', () => {
  it('writes every given line and refreshes the order and the project list', async () => {
    bulkSetLinesStockLocation.mockResolvedValue({ applied: 3 });
    let api: ReturnType<typeof useBulkSetLinesStockLocation> | null = null;
    render(
      <QueryClientProvider client={client}>
        <BulkHarness onReady={(value) => (api = value)} />
      </QueryClientProvider>,
    );

    await act(async () => {
      await api!.mutateAsync({ lineIds: ['l1', 'l2', 'l3'], stockLocation: 'BRW-BB' });
    });

    expect(bulkSetLinesStockLocation).toHaveBeenCalledWith(PSO_ID, ['l1', 'l2', 'l3'], 'BRW-BB');
    expect(invalidated).toEqual(
      expect.arrayContaining([salesOrderKey(PSO_ID), [SALES_ORDERS_KEY, PROJECT_ID]]),
    );
    expect(toast.success).toHaveBeenCalledWith('Stock location set on 3 lines');
  });
});
