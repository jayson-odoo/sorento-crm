/**
 * INTLOG-SPEED - the list query passes React Query's AbortSignal down, so a reload, a filter
 * change or a page change cancels the request it supersedes instead of stacking another one.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const getIntegrationLogs = vi.fn();
vi.mock('../services/integrationLogService', () => ({
  getIntegrationLogs: (...a: unknown[]) => getIntegrationLogs(...a),
  getIntegrationLog: vi.fn(),
  retryIntegrationLog: vi.fn(),
  updateIntegrationLog: vi.fn(),
}));

import { useIntegrationLogs } from './useIntegrationLogs';

describe('useIntegrationLogs - cancellation', () => {
  it('aborts the superseded request when the filters change', async () => {
    const signals: AbortSignal[] = [];
    getIntegrationLogs.mockImplementation((_p: unknown, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise(() => {});
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { rerender } = renderHook(
      ({ status }: { status?: string }) => useIntegrationLogs({ pageIndex: 0, pageSize: 50, status }),
      { wrapper, initialProps: { status: undefined as string | undefined } },
    );
    await waitFor(() => expect(signals).toHaveLength(1));
    expect(signals[0]).toBeInstanceOf(AbortSignal);

    rerender({ status: 'failed' });
    await waitFor(() => expect(signals).toHaveLength(2));
    await waitFor(() => expect(signals[0].aborted).toBe(true));
    expect(signals[1].aborted).toBe(false);
  });
});
