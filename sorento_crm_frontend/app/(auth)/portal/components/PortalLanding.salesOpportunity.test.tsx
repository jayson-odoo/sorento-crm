/**
 * The landing's Sales Opportunities card (UAC S2-10; plan 3.5, section 16).
 *
 * "A Sales Opportunities card on the landing only when `visible_form_types` has the kind."
 * Mocking pattern mirrors `PortalLanding.visibility.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
let searchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
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
  name: 'Darren Lee',
  phone_number: '60123456789',
  expires_at: '2026-09-01T00:00:00Z',
  portal_slug: 'darren',
};

function mockContact(visible: string[]) {
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue({
    ...ME,
    visible_form_types: visible,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams('');
  window.localStorage.clear();
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockResolvedValue([]);
  (listRequestsAsSummaries as ReturnType<typeof vi.fn>).mockResolvedValue([]);
});

describe('PortalLanding - Sales Opportunities card', () => {
  it('shows a Sales Opportunities link when the kind is visible', async () => {
    mockContact(['stock_inquiry', 'sales_opportunity']);
    render(<PortalLanding slug="darren" />);

    const link = await screen.findByRole('link', { name: /sales opportunities/i });
    expect(link.getAttribute('href')).toContain('/portal/sales_opportunity');
  });

  it('does not show it when the kind is not granted', async () => {
    mockContact(['stock_inquiry']);
    render(<PortalLanding slug="darren" />);

    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    expect(screen.queryByRole('link', { name: /sales opportunities/i })).toBeNull();
  });

  it('shows nothing sales-opportunity-shaped with an empty visible set', async () => {
    mockContact([]);
    render(<PortalLanding slug="darren" />);
    await screen.findByText(/no forms are available/i);
    expect(screen.queryByRole('link', { name: /sales opportunities/i })).toBeNull();
  });
});
