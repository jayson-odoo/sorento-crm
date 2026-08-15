/**
 * useRevisionEnabledMap - the thin react-query wrapper every office detail
 * page reads the office Revisions-tab kill switch through (UAC H2). Pins that
 * it is keyed once per tenant (shared cache across every form type) and that
 * a service-layer failure (extractApiError's message) surfaces as `isError`
 * rather than being swallowed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getRevisionEnabledMapMock = vi.fn();
vi.mock('./formRevisionsService', () => ({
  getRevisionEnabledMap: () => getRevisionEnabledMapMock(),
}));

import { useRevisionEnabledMap } from './useRevisionEnabledMap';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => vi.clearAllMocks());

describe('useRevisionEnabledMap', () => {
  it('is keyed once, tenant-wide, not per entity/type', async () => {
    getRevisionEnabledMapMock.mockResolvedValue({ stock_inquiry: true });
    const { result } = renderHook(() => useRevisionEnabledMap(), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual({ stock_inquiry: true }));
    expect(getRevisionEnabledMapMock).toHaveBeenCalledTimes(1);
  });

  it('surfaces the service-layer failure (extractApiError message) as isError, not a swallowed empty map', async () => {
    getRevisionEnabledMapMock.mockRejectedValue(
      new Error('Failed to load revision settings'),
    );
    const { result } = renderHook(() => useRevisionEnabledMap(), { wrapper });

    // The hook sets its own `retry: 1`, so the first failure retries once
    // (with backoff) before `isError` flips - give waitFor enough headroom.
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 3000 });
    expect(result.current.data).toBeUndefined();
    expect((result.current.error as Error).message).toBe(
      'Failed to load revision settings',
    );
  });
});
