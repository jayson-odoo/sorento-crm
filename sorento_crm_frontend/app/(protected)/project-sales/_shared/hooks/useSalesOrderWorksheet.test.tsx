/**
 * The worksheet read is its own query, keyed on its own id.
 *
 * Two things matter and neither is visible on the screen. The query must not fire before
 * there is an order to ask about, because a route param arrives a render late and a request
 * for `/sales-orders//worksheet` is a 404 the user reads as "this worksheet is broken". And
 * the key must carry the id, or opening a second sales order would be served the first one's
 * document from the cache - the worst possible failure for a screen whose whole job is to be
 * the document that goes into AutoCount.
 */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getSalesOrderWorksheet = vi.fn();

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('../services/projectSalesOrderService', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../services/projectSalesOrderService')>();
  return {
    ...actual,
    getSalesOrderWorksheet: (...args: unknown[]) => getSalesOrderWorksheet(...args),
  };
});

import { SALES_ORDER_WORKSHEET_KEY, useSalesOrderWorksheet } from './useProjectSalesOrders';

function harness() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryWrapper';
  return { client, Wrapper };
}

beforeEach(() => {
  getSalesOrderWorksheet.mockReset();
});

describe('useSalesOrderWorksheet', () => {
  it('asks nothing until there is a sales order to ask about', () => {
    const { Wrapper } = harness();

    renderHook(() => useSalesOrderWorksheet(undefined), { wrapper: Wrapper });

    expect(getSalesOrderWorksheet).not.toHaveBeenCalled();
  });

  it('passes the id through and caches the answer under it', async () => {
    getSalesOrderWorksheet.mockResolvedValue({ id: 'so-1', provisional_ref: 'PSO-000101' });
    const { client, Wrapper } = harness();

    renderHook(() => useSalesOrderWorksheet('so-1'), { wrapper: Wrapper });

    await waitFor(() => expect(getSalesOrderWorksheet).toHaveBeenCalledTimes(1));
    expect(getSalesOrderWorksheet).toHaveBeenCalledWith('so-1');
    expect(client.getQueryData([SALES_ORDER_WORKSHEET_KEY, 'so-1'])).toEqual({
      id: 'so-1',
      provisional_ref: 'PSO-000101',
    });
  });

  it('does not serve one order document for another', async () => {
    getSalesOrderWorksheet.mockResolvedValue({ id: 'x' });
    const { Wrapper } = harness();

    renderHook(() => useSalesOrderWorksheet('so-1'), { wrapper: Wrapper });
    renderHook(() => useSalesOrderWorksheet('so-2'), { wrapper: Wrapper });

    await waitFor(() => expect(getSalesOrderWorksheet).toHaveBeenCalledTimes(2));
  });
});
