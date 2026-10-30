/**
 * PS-REGISTER-CHECK-FIRST AC-R3: a dispute request toasts "Registered as secondary lead"
 * (was "Interest registered"); a join keeps "Request sent to the project owner".
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';

const createTakeoverRequest = vi.fn();

vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return {
    ...actual,
    createTakeoverRequest: (...args: unknown[]) => createTakeoverRequest(...args),
  };
});

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useTakeoverMutations } from './useProjects';

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  let api: ReturnType<typeof useTakeoverMutations> | null = null;
  function Harness() {
    api = useTakeoverMutations('p1');
    return null;
  }
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return () => api!;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useTakeoverMutations toasts', () => {
  it('AC-R3 a dispute request toasts "Registered as secondary lead"', async () => {
    createTakeoverRequest.mockResolvedValue({ id: 'r1', kind: 'dispute' });
    const get = mount();
    await act(async () => {
      await get().request.mutateAsync({ kind: 'dispute', reason: 'Found it in March.' });
    });
    expect(toast.success).toHaveBeenCalledWith('Registered as secondary lead');
  });

  it('AC-R3 a join request keeps "Request sent to the project owner"', async () => {
    createTakeoverRequest.mockResolvedValue({ id: 'r2', kind: 'join' });
    const get = mount();
    await act(async () => {
      await get().request.mutateAsync({ kind: 'join', reason: 'Add me.' });
    });
    expect(toast.success).toHaveBeenCalledWith('Request sent to the project owner');
  });
});
