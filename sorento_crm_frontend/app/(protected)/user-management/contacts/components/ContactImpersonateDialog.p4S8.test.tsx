/**
 * PORTAL-P4-REQUESTS S8: impersonating a contact that has a salesperson CRM user lands on the
 * salesperson's staff landing (Stock Inquiry staff list), never /my-requests, and writes no portal token.
 * A contact with no CRM user is unchanged (window.open portal_url).
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

const PORTAL_URL = 'http://localhost:3000/portal?token=IMP-TOKEN-123&impersonation=1';
const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body });

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

function mount() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ContactImpersonateDialog contact={{ id: 'c1', name: 'Eric Ng', phone_number: '60123456789' } as never} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.sessionStorage.clear();
  impersonationStore.setSession(null);
  window.open = vi.fn() as never;
});

describe('ContactImpersonateDialog S8', () => {
  it('salesperson contact: pushes the /my-requests landing and writes no portal token', async () => {
    answer('user-eric-1');
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(router.push.mock.calls.length + router.replace.mock.calls.length).toBeGreaterThan(0));
    const target = [...router.push.mock.calls, ...router.replace.mock.calls][0][0];
    expect(target).toBe('/my-requests');
    expect(window.sessionStorage.getItem('sorento.portalToken')).toBeNull();
    expect(window.localStorage.getItem('sorento.portalToken')).toBeNull();
    expect(impersonationStore.getState()?.targetUser.id).toBe('user-eric-1');
  });

  it('contact with no CRM user: unchanged, window.open(portal_url), no navigation', async () => {
    answer(null);
    mount();
    fireEvent.click(screen.getByRole('button', { name: 'Impersonate' }));
    await waitFor(() => expect(window.open).toHaveBeenCalledWith(PORTAL_URL, '_blank', 'noopener,noreferrer'));
    expect(router.push).not.toHaveBeenCalled();
    expect(router.replace).not.toHaveBeenCalled();
    expect(window.sessionStorage.getItem('sorento.portalToken')).toBeNull();
  });
});
