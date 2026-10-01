/**
 * L6: `usePermissions().isError` means "we could not find out", which is not the
 * same as "denied". A background refetch that fails over a good cached set is
 * still data (the user keeps what they had); only a failure with nothing loaded
 * is an error.
 */
import React from 'react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { usePermissions } from './usePermissions';

const fetchMyPermissions = vi.fn();
const failPermissions = async (): Promise<string[]> => {
  throw new Error('Failed to fetch permissions');
};
vi.mock('@/lib/permissions-service', () => ({
  fetchMyPermissions: () => fetchMyPermissions(),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u1' } }, status: 'authenticated' }),
}));

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => usePermissions(), { wrapper });
}

beforeEach(() => {
  fetchMyPermissions.mockReset();
});

describe('usePermissions().isError', () => {
  it('is true when the first load fails', async () => {
    fetchMyPermissions.mockImplementation(failPermissions);
    const { result } = setup();
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.isLoading).toBe(false);
  });

  it('stays false when a refetch fails over a loaded set', async () => {
    fetchMyPermissions.mockResolvedValueOnce(['a.view']);
    const { result } = setup();
    await waitFor(() => expect(result.current.permissionSet.has('a.view')).toBe(true));

    fetchMyPermissions.mockImplementation(failPermissions);
    await act(async () => {
      await result.current.refetch();
    });
    // React Query v5 notifies observers on a later tick: wait for the failed refetch
    // to reach the hook, or this asserts against the old success render.
    await waitFor(() => expect(result.current.error).toBeTruthy());
    expect(result.current.isError).toBe(false);
    expect(result.current.permissionSet.has('a.view')).toBe(true);
  });
});
