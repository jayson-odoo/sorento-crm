/** AFTER-SALES-P1 fix round 2 (R2-2): saving a complaint refreshes its service jobs (a resolution can raise one). */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('../services/complaintService', async (orig) => ({
  ...(await orig<object>()),
  updateComplaint: vi.fn(async () => ({})),
  updateComplaintAndReply: vi.fn(async () => ({})),
}));

import { useUpdateComplaint, useUpdateComplaintAndReply } from './useComplaints';

function wrap() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { spy, wrapper };
}

const keys = (spy: ReturnType<typeof vi.spyOn>) => spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey));

describe('complaint save refreshes service jobs', () => {
  it('useUpdateComplaint', async () => {
    const { spy, wrapper } = wrap();
    const { result } = renderHook(() => useUpdateComplaint(), { wrapper });
    result.current.mutate({ id: 'c-1', data: {} });
    await waitFor(() => expect(keys(spy)).toContain('["complaint-service-jobs"]'));
    expect(keys(spy)).toContain('["service-jobs"]');
  });

  it('useUpdateComplaintAndReply', async () => {
    const { spy, wrapper } = wrap();
    const { result } = renderHook(() => useUpdateComplaintAndReply(), { wrapper });
    result.current.mutate({ id: 'c-1', data: {} });
    await waitFor(() => expect(keys(spy)).toContain('["complaint-service-jobs"]'));
  });
});
