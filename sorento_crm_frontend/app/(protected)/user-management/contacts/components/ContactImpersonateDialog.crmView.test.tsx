/**
 * PORTAL-P3-ROLE-MENU round 6, F1 (P3-23, P3-24, P3-27): "Impersonate in portal" on a contact whose
 * start response carries crm_user_id starts CRM impersonation of that user, stores the
 * impersonation token (sessionStorage) and goes to /my-requests in THIS tab, no window.open.
 * crm_user_id null: exactly today's window.open(portal_url), nothing else.
 * Only apiFetch is mocked, so the real services adapt the raw API bodies.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const router = { push: vi.fn(), replace: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  usePathname: () => '/user-management/contacts',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { impersonationStore } from '@/lib/impersonation-store';
import { ContactImpersonateDialog } from './ContactImpersonateDialog';

const TOKEN_KEY = 'sorento.portalToken';
const PORTAL_URL = 'http://localhost:3000/portal?token=IMP-TOKEN-123&impersonation=1';
const CONTACT = { id: 'c1', name: 'Eric Ng', phone_number: '60123456789' };

function json(body: unknown) {
  return { ok: true, status: 200, json: async () => body };
}

function answer(crmUserId: string | null) {
  apiFetch.mockImplementation(async (url: string) => {
    if (url.includes('/contact-impersonation/start')) {
      return json({
        session_id: 's1',
        started_at: '2026-10-28T00:00:00Z',
        portal_url: PORTAL_URL,
        target_contact: { id: 'c1', name: 'Eric Ng', phone_number: '60123456789', space_id: 'sp1' },
        crm_user_id: crmUserId,
      });
    }
    if (url.includes('/user-management/impersonation/start')) {
      return json({
        session_id: 'u1',
        started_at: '2026-10-28T00:00:00Z',
        target_user: { id: crmUserId, name: 'Eric Ng', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
      });
    }
    return json({});
  });
}

let client: QueryClient;
function mount() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactImpersonateDialog contact={CONTACT as never} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

let open: ReturnType<typeof vi.fn>;
beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  impersonationStore.setSession(null);
  open = vi.fn();
  vi.stubGlobal('open', open);
  window.open = open as never;
});

describe('ContactImpersonateDialog with a linked salesperson user (F1)', () => {
  it('crm_user_id: starts CRM impersonation, stores the token in sessionStorage, goes to /my-requests, no window.open', async () => {
    answer('user-eric-1');
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(router.push.mock.calls.length + router.replace.mock.calls.length).toBeGreaterThan(0));
    const target = [...router.push.mock.calls, ...router.replace.mock.calls][0][0];
    expect(target).toBe('/my-requests');
    expect(open).not.toHaveBeenCalled();
    const urls = apiFetch.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('/user-management/impersonation/start'))).toBe(true);
    const body = JSON.parse(String(apiFetch.mock.calls.find((c) => String(c[0]).includes('/user-management/impersonation/start'))![1].body));
    expect(body.target_user_id).toBe('user-eric-1');
    expect(impersonationStore.getState()?.targetUser.id).toBe('user-eric-1');
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe('IMP-TOKEN-123');
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('crm_user_id null: window.open(portal_url) only, no CRM impersonation, no navigation', async () => {
    answer(null);
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(open).toHaveBeenCalledWith(PORTAL_URL, '_blank', 'noopener,noreferrer'));
    const urls = apiFetch.mock.calls.map((c) => String(c[0]));
    expect(urls.some((u) => u.includes('/user-management/impersonation/start'))).toBe(false);
    expect(router.push).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
    expect(impersonationStore.getState()).toBeNull();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});

describe('ContactImpersonateDialog cache and rollback (T1)', () => {
  it('the admin permission cache is invalidated before navigating to /my-requests', async () => {
    answer('user-eric-1');
    mount();
    client.setQueryData(['my-permissions'], ['admin.everything']);
    expect(client.getQueryState(['my-permissions'])?.isInvalidated).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/my-requests'));
    expect(client.getQueryState(['my-permissions'])?.isInvalidated).toBe(true);
  });

  it('navigation waits for the invalidation to finish', async () => {
    answer('user-eric-1');
    mount();
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    const spy = vi.spyOn(client, 'invalidateQueries').mockImplementation(() => gate);
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(router.push).not.toHaveBeenCalled();
    release();
    await waitFor(() => expect(router.push).toHaveBeenCalledWith('/my-requests'));
  });

  it('CRM impersonation start rejects: contact impersonation stopped, no token, no navigation', async () => {
    apiFetch.mockImplementation(async (url: string) => {
      if (url.includes('/contact-impersonation/start')) {
        return json({
          session_id: 's1', started_at: '2026-10-28T00:00:00Z', portal_url: PORTAL_URL,
          target_contact: { id: 'c1', name: 'Eric Ng', phone_number: '60123456789', space_id: 'sp1' },
          crm_user_id: 'user-eric-1',
        });
      }
      if (url.includes('/user-management/impersonation/start')) {
        return { ok: false, status: 500, json: async () => ({ detail: 'boom' }), text: async () => 'boom' };
      }
      return json({});
    });
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() =>
      expect(apiFetch.mock.calls.some((c) => String(c[0]).includes('/contact-impersonation/stop'))).toBe(true),
    );
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(router.push).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(impersonationStore.getState()).toBeNull();
  });
});
