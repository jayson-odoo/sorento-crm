/** AFTER-SALES-P1 fix round 2 (R2-1): a raise refreshes the complaint's jobs so the gear re-evaluates, then opens the job. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';

const push = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
const warning = vi.fn();
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: (...a: unknown[]) => warning(...a) } }));
let created = true;
vi.mock('../services/serviceJobService', async (orig) => ({
  ...(await orig<object>()),
  raiseServiceJob: vi.fn(async () => ({ job: { id: 'j-9' }, created })),
}));

import { useRaiseServiceJob } from './useServiceJobs';

function run() {
  const client = new QueryClient();
  const spy = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useRaiseServiceJob(), { wrapper });
  result.current.mutate('c-1');
  return spy;
}

describe('useRaiseServiceJob', () => {
  it('invalidates the complaint jobs and opens the new job', async () => {
    created = true;
    const spy = run();
    await waitFor(() => expect(push).toHaveBeenCalledWith('/complaint-management/service-jobs/j-9'));
    expect(spy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown }).queryKey))).toContain('["complaint-service-jobs"]');
  });

  it('says so and opens the live job when one already existed', async () => {
    created = false;
    push.mockClear();
    run();
    await waitFor(() => expect(warning).toHaveBeenCalledWith('This complaint already has a live service job.'));
    expect(push).toHaveBeenCalledWith('/complaint-management/service-jobs/j-9');
  });
});
