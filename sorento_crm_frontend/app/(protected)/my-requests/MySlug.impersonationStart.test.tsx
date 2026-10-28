/**
 * PORTAL-P3-ROLE-MENU round 10, C (replaces round 6b G1): a CRM impersonation of a salesperson with
 * NO impersonation token in this tab starts the contact impersonation itself (the target's
 * `respond_contact_id` from GET /users/me), writes the token from its portal_url to sessionStorage,
 * then runs the normal identity check and renders. A rejected start goes to verify with nothing
 * cleared. The admin's own localStorage token and slug are never touched.
 * Only apiFetch (CRM calls) and global fetch (portal calls) are mocked.
 */
import React, { StrictMode } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/my-requests',
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Admin' } }, status: 'authenticated' }),
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

import { impersonationStore } from '@/lib/impersonation-store';
import { fetchImpersonatedUserContactId } from '@/services/contactImpersonationService';
import { MySlug } from './MySlug';

const TOKEN_KEY = 'sorento.portalToken';
const SLUG_KEY = 'sorento.portalSlug';
const PORTAL_URL = 'http://localhost:3000/portal?token=NEW-IMP-TOKEN&impersonation=1';
const portalFetch = vi.fn();
let usersMeId = 'u-eric';

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body, text: async () => '' };
}

function crm(startOk: boolean) {
  apiFetch.mockImplementation(async (url: string) => {
    if (url.includes('/user-management/users/me')) {
      return ok({
        id: usersMeId,
        respond_contact_id: 'contact-eric',
        salesperson: { portal_kinds: ['stock_inquiry'], portal_slug: 'TARGETSLUG' },
      });
    }
    if (url.includes('/contact-impersonation/start')) {
      if (!startOk) return { ok: false, status: 500, json: async () => ({ detail: 'boom' }), text: async () => 'boom' };
      return ok({
        session_id: 'cs1',
        started_at: '2026-10-28T00:00:00Z',
        portal_url: PORTAL_URL,
        target_contact: { id: 'contact-eric', name: 'Eric', phone_number: '6012', space_id: 'sp1' },
        crm_user_id: 'u-eric',
      });
    }
    return ok({});
  });
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  usersMeId = 'u-eric';
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.localStorage.setItem(TOKEN_KEY, 'ADMIN-OWN-TOKEN');
  window.localStorage.setItem(SLUG_KEY, 'ADMINSLUG01');
  impersonationStore.setSession({
    sessionId: 's1',
    startedAt: '2026-10-28T00:00:00Z',
    targetUser: { id: 'u-eric', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
  });
  vi.stubGlobal('fetch', portalFetch);
  portalFetch.mockResolvedValue(ok({ portal_slug: 'TARGETSLUG' }));
});
afterEach(() => {
  vi.unstubAllGlobals();
  impersonationStore.setSession(null);
});

function startCall() {
  return apiFetch.mock.calls.find((c) => String(c[0]).includes('/contact-impersonation/start'));
}

describe('MySlug starts the contact impersonation itself (C)', () => {
  it('start ok and identity matches: token in sessionStorage, child renders, admin storage untouched', async () => {
    crm(true);
    mount();
    expect((await screen.findByTestId('child', {}, { timeout: 4000 })).getAttribute('data-slug')).toBe('TARGETSLUG');
    expect(JSON.parse(String(startCall()![1].body)).contact_id).toBe('contact-eric');
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe('NEW-IMP-TOKEN');
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
    expect(replace).not.toHaveBeenCalled();
  });

  it('start ok but the token is another contact\'s: only the session token is dropped, then verify', async () => {
    crm(true);
    portalFetch.mockResolvedValue(ok({ portal_slug: 'SOMEONEELSE' }));
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'), { timeout: 4000 });
    expect(startCall()).toBeDefined();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
  });

  it('start rejected: verify, nothing cleared, no token written', async () => {
    crm(false);
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'), { timeout: 4000 });
    expect(startCall()).toBeDefined();
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
    expect(window.localStorage.getItem(SLUG_KEY)).toBe('ADMINSLUG01');
    expect(screen.queryByTestId('child')).toBeNull();
  });
});

describe('MySlug one contact start per visit (round 11)', () => {
  function mountStrict() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // Preloaded, so the profile is settled on the first render and both StrictMode effect runs
    // reach the start call (an empty cache would hide the double run behind isLoading).
    client.setQueryData(['account-profile', 'u-eric'], {
      id: 'u-eric',
      respond_contact_id: 'contact-eric',
      salesperson: { portal_kinds: ['stock_inquiry'], portal_slug: 'TARGETSLUG' },
    });
    return render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <MySlug>{(slug) => <div data-testid="child" data-slug={slug} />}</MySlug>
        </QueryClientProvider>
      </StrictMode>,
    );
  }
  const startCount = () =>
    apiFetch.mock.calls.filter((c) => String(c[0]).includes('/contact-impersonation/start')).length;

  it('K1: under StrictMode the contact impersonation is started exactly once', async () => {
    crm(true);
    mountStrict();
    await screen.findByTestId('child', {}, { timeout: 4000 });
    expect(startCount()).toBe(1);
  });

  it('K2: a run cancelled before the start resolves writes no portal token', async () => {
    let release!: () => void;
    const gate = new Promise<void>((r) => { release = r; });
    crm(true);
    const base = apiFetch.getMockImplementation()!;
    apiFetch.mockImplementation(async (url: string, init?: unknown) => {
      if (String(url).includes('/contact-impersonation/start')) await gate;
      return base(url, init);
    });
    const view = mount();
    await waitFor(() => expect(startCount()).toBe(1));
    view.unmount();
    release();
    await new Promise((r) => setTimeout(r, 100));
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it('K3: /users/me answering as someone other than the view-as target: null from the service', async () => {
    crm(true);
    usersMeId = 'admin-1';
    expect(await fetchImpersonatedUserContactId()).toBeNull();
  });

  it('K3: /users/me answering as the target: its contact id', async () => {
    crm(true);
    usersMeId = 'u-eric';
    expect(await fetchImpersonatedUserContactId()).toBe('contact-eric');
  });

  it('K3: an ended view-as answers as the admin: MySlug goes to verify and starts nothing', async () => {
    crm(true);
    usersMeId = 'admin-1';
    mount();
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/my-requests/verify'), { timeout: 4000 });
    expect(startCount()).toBe(0);
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe('ADMIN-OWN-TOKEN');
  });
});
