/**
 * OCN-ORDER-CHANGE-NOTICE round 20 (scope change): the portal pages for Order Change Notice ship
 * in slice 2, so the portal landing's kind selector must NOT offer it even when it is in the
 * contact's visible kinds. (It joins LANDING_KINDS for the CRM, so the landing has to exclude it.)
 * Guard: green today, goes red if registering the kind leaks it into the landing.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('../lib/portal-client', async (importOriginal) => {
  const original = await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMeWithGrace: vi.fn(),
    fetchSubmissions: vi.fn(async () => []),
    portalLogout: vi.fn(),
    readPortalToken: vi.fn(() => 'tok-123'),
  };
});

import { fetchMeWithGrace } from '../lib/portal-client';
import { PortalLanding } from './PortalLanding';

function me(kinds: string[]) {
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue({
    contact_id: 'contact-1',
    space_id: 'space-1',
    name: 'Test Salesperson A',
    phone_number: '60123456789',
    expires_at: '2026-12-01T00:00:00Z',
    portal_slug: 'contact-x',
    visible_form_types: kinds,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});

describe('PortalLanding - Order Change Notice kind (slice 2 pages not shipped)', () => {
  it('does not offer "Order Change Notice" even when it is a visible kind', async () => {
    me(['stock_inquiry', 'order_change_notice']);
    render(<PortalLanding slug="contact-x" />);
    await waitFor(() => expect(fetchMeWithGrace).toHaveBeenCalled());
    await screen.findAllByText('Stock Inquiry');
    expect(screen.queryByText('Order Change Notice')).not.toBeInTheDocument();
    expect(screen.queryByText('order_change_notice')).not.toBeInTheDocument();
  });
});
