/**
 * PORTAL-P3-ROLE-MENU round 4, R3a: embedded in the CRM at /my-requests with no `type`, the
 * landing replaces the URL with ?type=<the kind it shows> (starred kind, else the first kind), so
 * the sidebar can highlight exactly one MY REQUESTS item. The portal itself keeps its URL.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const router = { push: vi.fn(), replace: vi.fn() };
let search = '';
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(search),
  usePathname: () => '/my-requests',
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMeWithGrace: vi.fn(),
    fetchSubmissions: vi.fn(),
    portalLogout: vi.fn(),
    readPortalToken: vi.fn(() => 'tok-123'),
  };
});
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options }: {
    value: string; onChange: (v: string) => void; options?: { value: string; label: string }[];
  }) => (
    <select data-testid="kind-picker" value={value} onChange={(e) => onChange(e.target.value)}>
      {(options ?? []).map((o) => (<option key={o.value} value={o.value}>{o.label}</option>))}
    </select>
  ),
}));
vi.mock('../lib/price-tag-request-service', () => ({ listRequestsAsSummaries: vi.fn() }));

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
  search = '';
  window.localStorage.clear();
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue(ME);
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listRequestsAsSummaries as ReturnType<typeof vi.fn>).mockResolvedValue([]);
});

describe('PortalLanding embedded, no ?type=', () => {
  it('replaces the URL with the first kind it shows (stock_inquiry)', async () => {
    render(<PortalLanding slug="ah-lim" embedded />);
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/my-requests?type=stock_inquiry'),
    );
  });

  it('replaces the URL with the starred kind', async () => {
    window.localStorage.setItem('sorento.portalDefaultTab.contact-1', 'complaint');
    render(<PortalLanding slug="ah-lim" embedded />);
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/my-requests?type=complaint'),
    );
    expect(router.replace).not.toHaveBeenCalledWith('/my-requests?type=stock_inquiry');
  });

  it('not embedded (the portal): the URL is left alone', async () => {
    render(<PortalLanding slug="ah-lim" />);
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    expect(router.replace).not.toHaveBeenCalledWith(expect.stringContaining('?type='));
  });
});

describe('PortalLanding kind switch (F2)', () => {
  it('embedded: picking another kind replaces the URL with that kind', async () => {
    search = 'type=stock_inquiry';
    render(<PortalLanding slug="ah-lim" embedded />);
    const picker = await screen.findByTestId('kind-picker');
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    fireEvent.change(picker, { target: { value: 'complaint' } });
    await waitFor(() =>
      expect(router.replace).toHaveBeenCalledWith('/my-requests?type=complaint'),
    );
  });

  it('not embedded (the portal): picking another kind does not replace the URL', async () => {
    search = 'type=stock_inquiry';
    render(<PortalLanding slug="ah-lim" />);
    const picker = await screen.findByTestId('kind-picker');
    fireEvent.change(picker, { target: { value: 'complaint' } });
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(router.replace).not.toHaveBeenCalledWith(expect.stringContaining('/my-requests'));
  });
});
