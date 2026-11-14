/**
 * OCN-ORDER-CHANGE-NOTICE round 20 (UAC I6, review B1): the portal pages for Order Change Notice
 * ship in slice 2, so the landing never offers it, even when it is in the contact's visible kinds
 * and even when a `?type=order_change_notice` deep link names it. GUARD: green on HEAD; goes red
 * when the PORTAL_PAGES_PENDING filter in PortalLanding.landingKindsFor is removed.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

let searchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => searchParams,
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

import { fetchMeWithGrace, fetchSubmissions } from '../lib/portal-client';
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

const askedForOcn = () =>
  (fetchSubmissions as ReturnType<typeof vi.fn>).mock.calls.some((c) =>
    JSON.stringify(c).includes('order_change_notice'),
  );

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  searchParams = new URLSearchParams('');
});

describe('PortalLanding - Order Change Notice is never offered (slice 2 pages not shipped)', () => {
  it('the kind selector lists the other visible kinds but not "Order Change Notice"', async () => {
    me(['stock_inquiry', 'complaint', 'order_change_notice']);
    render(<PortalLanding slug="contact-x" />);
    const trigger = await screen.findByRole('combobox');
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    trigger.click();
    expect((await screen.findAllByText('Complaint')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('option', { name: /Order Change Notice/i })).toBeNull();
    expect(screen.queryByText('Order Change Notice')).toBeNull();
    expect(screen.queryByText('order_change_notice')).toBeNull();
    expect(askedForOcn()).toBe(false);
  });

  it('a ?type=order_change_notice deep link falls back to a visible kind: no notice list or form', async () => {
    searchParams = new URLSearchParams('type=order_change_notice');
    me(['stock_inquiry', 'order_change_notice']);
    render(<PortalLanding slug="contact-x" />);
    await waitFor(() => expect(fetchSubmissions).toHaveBeenCalled());
    expect((await screen.findAllByText('Stock Inquiry')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Order Change Notice')).toBeNull();
    expect(screen.queryByRole('link', { name: /Order Change Notice/i })).toBeNull();
    expect(askedForOcn()).toBe(false);
  });
});
