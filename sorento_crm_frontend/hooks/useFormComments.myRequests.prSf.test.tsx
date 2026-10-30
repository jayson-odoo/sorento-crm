/**
 * PORTAL-P4-REQUESTS S3 (P4-25): a LIMITED Purchase Request / Sponsorship Form user posts a comment through `/api/v1/my-requests/...comments`
 * (the portal path), staff keep `/api/v1/form-comments/...`. Asserted at the HTTP seam (`apiFetch`).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { useAddFormComment } from './useFormComments';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async () =>
    new Response(JSON.stringify({ comment: { id: 'cm1', body: 'hi', created_at: '2026-10-28T00:00:00' }, delivery: 'sent' }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  );
});

async function post(kind: string) {
  const { result } = renderHook(() => useAddFormComment(kind as never, 'pr-1'), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ body: 'hi', files: [] }).catch(() => {});
  });
  await waitFor(() => expect(apiFetch).toHaveBeenCalled());
  return apiFetch.mock.calls.map((c) => [String(c[0]), (c[1] as RequestInit | undefined)?.method ?? 'GET']);
}

describe.each([
  ['purchase_request', 'procurement.purchase_requests'],
  ['sponsorship_form', 'procurement.sponsorship_forms'],
])('posting a comment on a %s', (kind, base) => {
  it('staff user (control): POST /api/v1/form-comments/<kind>/pr-1', async () => {
    held = new Set([`${base}.view`]);
    const calls = await post(kind);
    expect(calls.some(([u]) => u.startsWith('/api/v1/my-requests/'))).toBe(false);
    expect(calls.some(([u, m]) => u.startsWith(`/api/v1/form-comments/`) && u.includes('pr-1') && m === 'POST')).toBe(true);
  });
});
