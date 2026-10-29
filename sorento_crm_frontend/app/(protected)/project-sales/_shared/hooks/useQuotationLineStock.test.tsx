/** QUOTE-STOCK-AGENT-LOC: `useQuotationLineStock(productId)` reads the service once per product. */
import React, { type ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getQuotationLineStock = vi.fn();
vi.mock('../services/fulfilmentPlanningService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/fulfilmentPlanningService')>();
  return { ...actual, getQuotationLineStock: (...args: unknown[]) => getQuotationLineStock(...args) };
});

import * as hooks from './useFulfilmentPlanning';

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => vi.clearAllMocks());

describe('useQuotationLineStock', () => {
  it('calls the service with the product id and exposes the detail', async () => {
    getQuotationLineStock.mockResolvedValue({ available_qty: '7' });
    const { result } = renderHook(
      () => (hooks as unknown as { useQuotationLineStock: (id: string) => { data: unknown; isSuccess: boolean } })
        .useQuotationLineStock('prod-1'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getQuotationLineStock).toHaveBeenCalledWith('prod-1');
    expect(result.current.data).toEqual({ available_qty: '7' });
  });

  it('keeps a null answer as null data', async () => {
    getQuotationLineStock.mockResolvedValue(null);
    const { result } = renderHook(
      () => (hooks as unknown as { useQuotationLineStock: (id: string) => { data: unknown; isSuccess: boolean } })
        .useQuotationLineStock('prod-2'),
      { wrapper: wrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });
});
