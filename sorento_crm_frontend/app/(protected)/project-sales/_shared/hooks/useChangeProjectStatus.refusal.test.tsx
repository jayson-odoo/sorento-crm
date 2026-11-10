/**
 * The status move hook shows a refused move's server message as an error toast.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { toast } from '@/lib/toast';

const changeProjectStatus = vi.fn();
vi.mock('../services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/projectService')>();
  return { ...actual, changeProjectStatus: (...args: unknown[]) => changeProjectStatus(...args) };
});
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { useChangeProjectStatus } from './useProjects';

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  let api: ReturnType<typeof useChangeProjectStatus> | null = null;
  function Harness() {
    api = useChangeProjectStatus();
    return null;
  }
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return () => api!;
}

function coded(message: string, code: string) {
  return Object.assign(new Error(message), { code });
}

beforeEach(() => vi.clearAllMocks());

describe('useChangeProjectStatus refusals', () => {
  it('a refused move shows the server message as an error toast', async () => {
    changeProjectStatus.mockRejectedValue(coded('Not allowed.', 'something_else'));
    const get = mount();
    await act(async () => {
      await get().mutateAsync({ projectId: 'p1', toStatusId: 's-spec' }).catch(() => undefined);
    });
    expect(toast.error).toHaveBeenCalledWith('Not allowed.');
  });
});
