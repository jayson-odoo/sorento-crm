/**
 * PORTAL-P3-ROLE-MENU round 4, R1: pin the hook's {salesperson, isLoading, isError} states.
 * Mutation guards (each case fails if the named mutation is applied to the hook):
 *  - session loading        -> isLoading true : catches "force isLoading false"
 *  - query pending          -> isLoading true : catches "force isLoading false"
 *  - answered null          -> isLoading false: catches "force isLoading true"
 *  - answered salesperson   -> mapped fields  : catches "force isLoading true" and a wrong field map
 *  - fetch throws           -> isError true, isLoading false: catches "force isLoading true"
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const session: { data: unknown; status: 'loading' | 'authenticated' | 'unauthenticated' } = {
  data: null,
  status: 'authenticated',
};
vi.mock('next-auth/react', () => ({ useSession: () => session }));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { useAccountProfileForHeader } from './useAccountProfileForHeader';

function run() {
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 1 } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useAccountProfileForHeader(), { wrapper });
}

const ok = (body: unknown) => ({ ok: true, json: async () => body });

beforeEach(() => {
  vi.clearAllMocks();
  session.data = { user: { name: 'S' } };
  session.status = 'authenticated';
});

describe('useAccountProfileForHeader states', () => {
  it('session loading: isLoading true and no request', () => {
    session.status = 'loading';
    const { result } = run();
    expect(result.current.isLoading).toBe(true);
    expect(result.current.salesperson).toBeNull();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it('session ready, query pending: isLoading true', () => {
    apiFetch.mockReturnValue(new Promise(() => {}));
    const { result } = run();
    expect(result.current.isLoading).toBe(true);
    expect(result.current.isError).toBe(false);
  });

  it('answer with salesperson null: settled, salesperson null', async () => {
    apiFetch.mockResolvedValue(ok({ name: 'X', salesperson: null }));
    const { result } = run();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.salesperson).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it('answer with a salesperson block: mapped to portalKinds and portalSlug', async () => {
    apiFetch.mockResolvedValue(
      ok({ salesperson: { portal_kinds: ['stock_inquiry', 'complaint'], portal_slug: 'NT8D6BFC45' } }),
    );
    const { result } = run();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.salesperson).toEqual({
      portalKinds: ['stock_inquiry', 'complaint'],
      portalSlug: 'NT8D6BFC45',
    });
  });

  it('fetch throws: isError true and isLoading false', async () => {
    apiFetch.mockRejectedValue(new Error('network'));
    const { result } = run();
    await waitFor(() => expect(result.current.isError).toBe(true), { timeout: 5000 });
    expect(result.current.isLoading).toBe(false);
    expect(result.current.salesperson).toBeNull();
  });
});
