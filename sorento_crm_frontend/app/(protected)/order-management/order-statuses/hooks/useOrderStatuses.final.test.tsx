/**
 * FILTER-MULTISELECT PR4b: the Order statuses "Final" choice rides the list request end to end. The
 * service puts `is_final_status` on the URL (the backend route's param), and the list hook refetches
 * when the choice changes instead of serving the cached page for the other choice.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { getOrderStatuses } from '../services/orderStatusService';
import { useOrderStatuses } from './useOrderStatuses';

const base = { pageIndex: 0, pageSize: 50, sorting: [], searchQuery: '' };
const lastUrl = () => String(apiFetch.mock.calls[apiFetch.mock.calls.length - 1][0]);
const paramOf = (key: string) => new URL(lastUrl(), 'http://x').searchParams.get(key);

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockResolvedValue({ ok: true, json: async () => ({ data: [], pagination: { total: 0, page: 1, limit: 50 } }) });
});

describe('Order statuses - Final filter on the request', () => {
  it('the service sends is_final_status=true / false and nothing when unset', async () => {
    await getOrderStatuses({ ...base, is_final_status: true } as never);
    expect(paramOf('is_final_status')).toBe('true');
    await getOrderStatuses({ ...base, is_final_status: false } as never);
    expect(paramOf('is_final_status')).toBe('false');
    await getOrderStatuses(base as never);
    expect(paramOf('is_final_status')).toBeNull();
  });

  it('the hook refetches when the Final choice changes', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { rerender } = renderHook(
      ({ params }: { params: Record<string, unknown> }) => useOrderStatuses(params as never),
      { wrapper, initialProps: { params: { ...base, is_final_status: true } } },
    );
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
    expect(paramOf('is_final_status')).toBe('true');
    rerender({ params: { ...base, is_final_status: false } });
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
    expect(paramOf('is_final_status')).toBe('false');
  });
});
