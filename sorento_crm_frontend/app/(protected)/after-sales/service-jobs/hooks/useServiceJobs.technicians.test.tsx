/** R6-3: assigning a technician refreshes the technician list, whose in-use flag would otherwise go stale. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('../services/serviceJobService', async (orig) => ({
  ...(await orig<object>()),
  assignServiceJob: vi.fn(async () => ({})),
  createServiceJob: vi.fn(async () => ({})),
}));

import { useServiceJobActions } from './useServiceJobs';

describe('job moves refresh the technicians list', () => {
  it('assign', async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, 'invalidateQueries');
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useServiceJobActions(), { wrapper });
    result.current.assign.mutate({ id: 'j-1', technicianId: 't-1' });
    await waitFor(() =>
      expect(spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))).toContain('["technicians"]'),
    );
  });
});
