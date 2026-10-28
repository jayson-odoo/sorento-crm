/**
 * PORTAL-P3-ROLE-MENU round 10, B: the legacy /portal page, opened with an impersonation token whose
 * /me carries `crm_user_id`, starts the CRM impersonation of that user, keeps the tab's token and
 * goes to /my-requests. A rejected start or a null crm_user_id keeps today's legacy landing.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const router = { replace: vi.fn(), push: vi.fn() };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams('token=IMP-TOKEN&impersonation=1'),
  usePathname: () => '/portal',
}));

const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({ apiFetch: (...a: unknown[]) => apiFetch(...a) }));

vi.mock('./components/PortalLanding', () => ({ PortalLanding: () => <div data-testid="legacy-landing" /> }));
vi.mock('./components/PortalVerifyCard', () => ({ PortalVerifyCard: () => <div data-testid="verify-card" /> }));

const me = vi.fn();
vi.mock('./lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('./lib/portal-client')>();
  return { ...original, fetchMeWithGrace: (...a: unknown[]) => me(...a) };
});

import { impersonationStore } from '@/lib/impersonation-store';
import PortalPage from './page';

const TOKEN_KEY = 'sorento.portalToken';

function meBody(crmUserId: string | null) {
  return {
    contact_id: 'c1', space_id: 's1', name: 'Eric', phone_number: '6012',
    expires_at: '2026-11-27T00:00:00Z', portal_slug: 'ERICSLUG01',
    visible_form_types: ['stock_inquiry'],
    impersonation: { session_id: 'cs1', admin_user_id: 'a1', admin_name: 'Admin', admin_email: 'a@x.test', started_at: 'x' },
    crm_user_id: crmUserId,
  };
}

function crmStart(ok: boolean) {
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/user-management/impersonation/start')) {
      if (!ok) return { ok: false, status: 500, json: async () => ({ detail: 'boom' }), text: async () => 'boom' };
      return {
        ok: true, status: 200, text: async () => '',
        json: async () => ({
          session_id: 'u1', started_at: '2026-10-28T00:00:00Z',
          target_user: { id: 'u-eric', name: 'Eric', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}), text: async () => '' };
  });
}

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PortalPage />
    </QueryClientProvider>,
  );
}

const startCalls = () => apiFetch.mock.calls.filter((c) => String(c[0]).includes('/user-management/impersonation/start'));

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  impersonationStore.setSession(null);
});

describe('legacy /portal impersonation entry (B)', () => {
  it('crm_user_id: CRM impersonation started, tab token kept, goes to /my-requests', async () => {
    me.mockResolvedValue(meBody('u-eric'));
    crmStart(true);
    mount();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/my-requests'));
    expect(JSON.parse(String(startCalls()[0][1].body)).target_user_id).toBe('u-eric');
    expect(impersonationStore.getState()?.targetUser.id).toBe('u-eric');
    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe('IMP-TOKEN');
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(screen.queryByTestId('legacy-landing')).toBeNull();
  });

  it('CRM start rejected: today\'s legacy landing renders', async () => {
    me.mockResolvedValue(meBody('u-eric'));
    crmStart(false);
    mount();
    expect(await screen.findByTestId('legacy-landing')).toBeInTheDocument();
    expect(startCalls()).toHaveLength(1);
    expect(router.replace).not.toHaveBeenCalledWith('/my-requests');
  });

  it('crm_user_id null: legacy landing, no CRM start', async () => {
    me.mockResolvedValue(meBody(null));
    crmStart(true);
    mount();
    expect(await screen.findByTestId('legacy-landing')).toBeInTheDocument();
    expect(startCalls()).toHaveLength(0);
    expect(router.replace).not.toHaveBeenCalledWith('/my-requests');
  });
});
