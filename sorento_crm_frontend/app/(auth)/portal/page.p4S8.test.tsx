/**
 * PORTAL-P4-REQUESTS S8: the legacy /portal page opened with an impersonation token whose /me carries
 * crm_user_id enters the CRM view and goes to /my-requests (the redirecting landing) with no portal token.
 * crm_user_id null keeps today's legacy landing.
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

const meBody = (crmUserId: string | null) => ({
  contact_id: 'c1', space_id: 's1', name: 'Test Salesperson A', phone_number: '6012',
  expires_at: '2026-11-27T00:00:00Z', portal_slug: 'ERICSLUG01',
  visible_form_types: ['stock_inquiry'],
  impersonation: { session_id: 'cs1', admin_user_id: 'a1', admin_name: 'Admin', admin_email: 'a@x.test', started_at: 'x' },
  crm_user_id: crmUserId,
});

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PortalPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  impersonationStore.setSession(null);
  apiFetch.mockImplementation(async (url: string) => {
    if (String(url).includes('/user-management/impersonation/start')) {
      return {
        ok: true, status: 200, text: async () => '',
        json: async () => ({
          session_id: 'u1', started_at: '2026-10-28T00:00:00Z',
          target_user: { id: 'u-sales-a', name: 'Test Salesperson A', email: 'e@x.test', avatar: null, role_name: 'salesperson' },
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({}), text: async () => '' };
  });
});

describe('legacy /portal impersonation entry S8', () => {
  it('crm_user_id: goes to /my-requests and writes no portal token in either storage', async () => {
    me.mockResolvedValue(meBody('u-sales-a'));
    mount();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith('/my-requests'));
    expect(window.localStorage.getItem('sorento.portalToken')).toBeNull();
    expect(window.sessionStorage.getItem('sorento.portalToken')).toBeNull();
  });
  it('crm_user_id null: legacy landing unchanged, no redirect', async () => {
    me.mockResolvedValue(meBody(null));
    mount();
    expect(await screen.findByTestId('legacy-landing')).toBeInTheDocument();
    // (the page strips the token from the address bar with replace('/'); that is today's behaviour)
    expect(router.replace).not.toHaveBeenCalledWith('/my-requests');
  });
});
