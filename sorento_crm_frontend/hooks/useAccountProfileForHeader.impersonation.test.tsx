/**
 * PORTAL-P3-ROLE-MENU round 6, F2 (P3-25): under an active CRM impersonation session the salesperson
 * the sidebar / MySlug use is the TARGET's. lib/api attaches X-Impersonate-User-Id only to
 * `/api/v1/` URLs, so the mocked apiFetch below answers the target's profile only for such a URL
 * (and the admin's own for any other) - the hook must read `salesperson` through an /api/v1/ URL.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Admin' } }, status: 'authenticated' }),
}));

import { impersonationStore } from '@/lib/impersonation-store';

const apiFetch = vi.fn(async (url: string) => {
  const impersonating = !!impersonationStore.getState() && url.includes('/api/v1/');
  const body = impersonating
    ? { name: 'Eric', email: 'e@x.test', salesperson: { portal_kinds: ['stock_inquiry'], portal_slug: 'TARGETSLUG' } }
    : { name: 'Admin', email: 'a@x.test', salesperson: null };
  return { ok: true, status: 200, json: async () => body };
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...(a as [string])) }));

import { useAccountProfileForHeader } from './useAccountProfileForHeader';

function run() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useAccountProfileForHeader(), { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  impersonationStore.setSession(null);
});
afterEach(() => impersonationStore.setSession(null));

describe('useAccountProfileForHeader under CRM impersonation (F2)', () => {
  it('impersonating: salesperson is the target\'s', async () => {
    impersonationStore.setSession({
      sessionId: 's1',
      startedAt: '2026-10-28T00:00:00Z',
      targetUser: { id: 'u-eric', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
    });
    const { result } = run();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.salesperson).toEqual({
      portalKinds: ['stock_inquiry'],
      portalSlug: 'TARGETSLUG',
    });
  });

  it('not impersonating: the admin has no salesperson block', async () => {
    const { result } = run();
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.salesperson).toBeNull();
  });
});
