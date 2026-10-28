/**
 * PORTAL-P4-REQUESTS S1 (P4-25): a LIMITED user deleting their own comment calls the portal's route,
 * DELETE /api/v1/my-requests/submissions/{kind}/{id}/comments/{comment_id}, not the staff deferred delete.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));
vi.mock('next-auth/react', async () => {
  const { createContext } = await import('react');
  return { SessionContext: createContext({ data: { user: { name: 'Pat' } }, status: 'authenticated' }) };
});

const calls: Array<{ url: string; method: string }> = [];
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string, init?: RequestInit) => {
    const method = (init?.method ?? 'GET').toUpperCase();
    calls.push({ url, method });
    const body = method === 'GET'
      ? { items: [{ id: 'c1', body: 'mine', kind: 'comment', author_name: 'Pat', author_kind: 'submitter', can_delete: true, can_edit: true, can_reply: true, created_at: '2026-10-09T01:00:00', attachments: [], deleted: false }] }
      : {};
    return new Response(method === 'DELETE' ? null : JSON.stringify(body), {
      status: method === 'DELETE' ? 204 : 200,
      headers: { 'content-type': 'application/json' },
    });
  },
}));

import { FormComments } from './FormComments';

beforeEach(() => { calls.length = 0; });

function mount(slugs: string[]) {
  held = new Set(slugs);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <FormComments kind="stock_inquiry" entityId="si-1" />
    </QueryClientProvider>,
  );
}

describe('deleting a comment', () => {
  it('limited user: DELETE /api/v1/my-requests/submissions/stock_inquiry/si-1/comments/c1', async () => {
    mount(['procurement.stock_inquiries.view_own']);
    await userEvent.click(await screen.findByRole('button', { name: /Delete/ }));
    await waitFor(() =>
      expect(calls).toContainEqual({ url: '/api/v1/my-requests/submissions/stock_inquiry/si-1/comments/c1', method: 'DELETE' }),
    );
    expect(calls.some((c) => c.url.includes('/deferred') || c.url.includes('pending-actions'))).toBe(false);
  });
});
