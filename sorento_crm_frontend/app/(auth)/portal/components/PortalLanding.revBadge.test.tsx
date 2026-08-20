/**
 * Portal list cards surface the revision state (portal revision UX): a row
 * that has been revised carries a "Rev N" badge next to its document number
 * and reads "Revised <date>" instead of the created date. A never-revised row
 * shows neither.
 *
 * Mocking pattern mirrors `PortalLandingRevise.test.tsx`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import type { PortalSubmissionSummary } from '../lib/portal-client';

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('../lib/portal-client', async (importOriginal) => {
  const original =
    await importOriginal<typeof import('../lib/portal-client')>();
  return {
    ...original,
    fetchMeWithGrace: vi.fn(),
    fetchSubmissions: vi.fn(),
    fetchSubmission: vi.fn(),
    portalLogout: vi.fn(),
    readPortalToken: vi.fn(() => 'tok-123'),
  };
});

import { fetchMeWithGrace, fetchSubmissions } from '../lib/portal-client';
import { PortalLanding } from './PortalLanding';

const REVISED_ROW: PortalSubmissionSummary = {
  id: 'si-revised',
  kind: 'stock_inquiry',
  title: 'Stock inquiry',
  document_number: 'SI-26-0184',
  reference: 'SI-26-0184',
  status: 'pending_purchasing',
  is_editable: false,
  is_draft: false,
  created_at: '2026-07-01T00:00:00Z',
  revision_no: 2,
  last_revised_at: '2026-07-20T00:00:00Z',
  product_code: 'ABC-123',
};

const UNREVISED_ROW: PortalSubmissionSummary = {
  id: 'si-fresh',
  kind: 'stock_inquiry',
  title: 'Stock inquiry',
  document_number: 'SI-26-0200',
  reference: 'SI-26-0200',
  status: 'pending_purchasing',
  is_editable: false,
  is_draft: false,
  created_at: '2026-07-05T00:00:00Z',
  revision_no: 0,
  last_revised_at: null,
  product_code: 'XYZ-999',
};

beforeEach(() => {
  vi.clearAllMocks();
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue({
    contact_id: 'contact-1',
    space_id: 'space-1',
    name: 'Darren Lee',
    phone_number: '60123456789',
    expires_at: '2026-09-01T00:00:00Z',
    portal_slug: 'darren',
  });
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockImplementation(
    async (kind: string) =>
      kind === 'stock_inquiry' ? [REVISED_ROW, UNREVISED_ROW] : [],
  );
});

describe('PortalLanding - revision badge and date on the submission card', () => {
  it('shows "Rev 2" and a Revised date line for a revised row', async () => {
    render(<PortalLanding slug="darren" />);
    await screen.findByText('SI-26-0184');

    expect(screen.getByText('Rev 2')).toBeInTheDocument();
    expect(screen.getByText(/^Revised /)).toBeInTheDocument();
  });

  it('shows neither the badge nor a Revised line for an unrevised row', async () => {
    render(<PortalLanding slug="darren" />);
    const freshCard = await screen.findByText('SI-26-0200');

    expect(screen.queryByText('Rev 0')).toBeNull();
    // Only the revised row's "Revised ..." line exists; the fresh row keeps
    // its plain created-date line instead.
    await waitFor(() =>
      expect(screen.getAllByText(/^Revised /)).toHaveLength(1),
    );
    expect(freshCard).toBeInTheDocument();
  });
});
