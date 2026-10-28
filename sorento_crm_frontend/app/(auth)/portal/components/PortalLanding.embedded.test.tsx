/**
 * PORTAL-P3-ROLE-MENU P3-16, P3-18: inside the CRM shell (`embedded`) the landing shows no portal
 * header and no portal log-out (the CRM user menu is the only one); the portal itself is unchanged.
 * Mocking pattern mirrors `PortalLanding.conversation.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const router = { push: vi.fn(), replace: vi.fn() };
let searchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
  usePathname: () => '/my-requests',
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMeWithGrace: vi.fn(),
    fetchSubmissions: vi.fn(),
    fetchSubmission: vi.fn(),
    portalLogout: vi.fn(),
    readPortalToken: vi.fn(() => 'tok-123'),
  };
});

vi.mock('../lib/price-tag-request-service', () => ({
  listRequestsAsSummaries: vi.fn(),
}));

import { fetchMeWithGrace, fetchSubmissions } from '../lib/portal-client';
import { listRequestsAsSummaries } from '../lib/price-tag-request-service';
import { PortalLanding } from './PortalLanding';

const ME = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Agent Lim',
  phone_number: '60123456789',
  expires_at: '2026-10-01T00:00:00Z',
  portal_slug: 'ah-lim',
  visible_form_types: ['stock_inquiry', 'complaint'],
};

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams('type=stock_inquiry');
  window.localStorage.clear();
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue(ME);
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listRequestsAsSummaries as ReturnType<typeof vi.fn>).mockResolvedValue([]);
});

describe('PortalLanding embedded', () => {
  it('not embedded (the portal): welcome header and Log out are there', async () => {
    render(<PortalLanding slug="ah-lim" />);
    expect(await screen.findByRole('button', { name: 'Log out' })).toBeInTheDocument();
    expect(screen.getByText(/Welcome, Agent Lim/)).toBeInTheDocument();
  });

  it('embedded: the list renders, with no portal log-out and no portal header', async () => {
    render(<PortalLanding slug="ah-lim" {...({ embedded: true } as object)} />);
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    await screen.findByRole('combobox');
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull();
    expect(screen.queryByText(/Welcome/)).toBeNull();
  });
});
