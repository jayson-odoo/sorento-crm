/**
 * PORTAL-P4-REQUESTS S2 (P4-25): a LIMITED user posts a complaint comment through `/api/v1/my-requests/...comments`
 * (the portal path); staff keep `/api/v1/form-comments/...`. Asserted at the HTTP seam (`apiFetch`).
 * Same shape as useFormComments.myRequests.test.tsx (Stock Inquiry).
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

import { useAddFormComment, useFormCommentsQuery } from './useFormComments';

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    {children}
  </QueryClientProvider>
);

beforeEach(() => {
  apiFetch.mockReset();
  apiFetch.mockImplementation(async () =>
    new Response(JSON.stringify({ comment: { id: 'cm1', body: 'hi', created_at: '2026-10-28T00:00:00' }, delivery: 'sent', items: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
  );
});

const seen = () => apiFetch.mock.calls.map((c) => [String(c[0]), (c[1] as RequestInit | undefined)?.method ?? 'GET']);

async function post() {
  const { result } = renderHook(() => useAddFormComment('complaint', 'cp-1'), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ body: 'hi', files: [] }).catch(() => {});
  });
  await waitFor(() => expect(apiFetch).toHaveBeenCalled());
  return seen();
}

describe('posting a comment on a complaint', () => {
  it('limited user: POST /api/v1/my-requests/submissions/complaint/cp-1/comments', async () => {
    held = new Set(['complaint_management.complaints.view_own']);
    const calls = await post();
    expect(calls).toContainEqual(['/api/v1/my-requests/submissions/complaint/cp-1/comments', 'POST']);
    expect(calls.some(([u, m]) => u.startsWith('/api/v1/form-comments/') && m === 'POST')).toBe(false);
  });

  it('staff user (control): POST /api/v1/form-comments/complaint/cp-1', async () => {
    held = new Set(['complaint_management.complaints.view']);
    const calls = await post();
    expect(calls).toContainEqual(['/api/v1/form-comments/complaint/cp-1', 'POST']);
    expect(calls.some(([u]) => u.startsWith('/api/v1/my-requests/'))).toBe(false);
  });
});

describe('reading the thread on a complaint', () => {
  it('limited user: GET /api/v1/my-requests/submissions/complaint/cp-1/comments', async () => {
    held = new Set(['complaint_management.complaints.view_own']);
    renderHook(() => useFormCommentsQuery('complaint', 'cp-1'), { wrapper });
    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(seen()).toContainEqual(['/api/v1/my-requests/submissions/complaint/cp-1/comments', 'GET']);
    expect(seen().some(([u]) => u.startsWith('/api/v1/form-comments/'))).toBe(false);
  });
});
