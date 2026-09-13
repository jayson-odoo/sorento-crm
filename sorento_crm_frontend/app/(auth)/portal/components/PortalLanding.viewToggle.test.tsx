/**
 * PLAN-portal-price-tag-journey-r8, Round 3 (R3-2, AC-R9).
 *
 * REPLACES the D-L5/AC-L7 contract this file used to pin (viewport-based
 * default, list view = one custom `<SubmissionRow>` line per submission):
 *
 *  - Cards is the default at EVERY width when nothing is stored - the
 *    `window.matchMedia('(min-width: 768px)')` viewport default is gone.
 *  - A stored choice still wins (unaffected by R3-2).
 *  - List view renders the repo DataGrid (`role="table"`), one column per
 *    field of the kind (Form Number, Status, the kind's own fields, Need by,
 *    Created), not the old `<ul>` of `SubmissionRow`.
 *
 * Mocking pattern mirrors `PortalLanding.revBadge.test.tsx` (no price-tag
 * mock needed - `visible_form_types` is absent from `ME`, so
 * `landingKindsFor` never reaches for it).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { PortalSubmissionSummary } from '../lib/portal-client';

const push = vi.fn();
const replace = vi.fn();
const router = { push, replace };
let searchParams = new URLSearchParams('');
vi.mock('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => searchParams,
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

const ME = {
  contact_id: 'contact-1',
  space_id: 'space-1',
  name: 'Darren Lee',
  phone_number: '60123456789',
  expires_at: '2026-09-01T00:00:00Z',
  portal_slug: 'darren',
};

const ROW: PortalSubmissionSummary = {
  id: 'si-1',
  kind: 'stock_inquiry',
  title: 'Stock inquiry',
  document_number: 'SI-26-0184',
  reference: 'SI-26-0184',
  status: 'pending_purchasing',
  is_editable: false,
  is_draft: false,
  created_at: '2026-07-01T00:00:00Z',
  product_code:
    'ZZT-A-VERY-LONG-PRODUCT-CODE-THAT-WOULD-WRAP-A-NARROW-ROW-IF-LET-TO',
};

/** `window.matchMedia('(min-width: 768px)')` - R3-2 removes the viewport
 *  default entirely, so this is only used to prove BOTH widths land on
 *  Cards, not to pick a different expectation per width. */
function mockViewportAtLeast768(matches: boolean) {
  const original = window.matchMedia;
  window.matchMedia = ((query: string) => ({
    matches: query.includes('768px') ? matches : false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  searchParams = new URLSearchParams('');
  window.localStorage.clear();
  (fetchMeWithGrace as ReturnType<typeof vi.fn>).mockResolvedValue(ME);
  (fetchSubmissions as ReturnType<typeof vi.fn>).mockImplementation(
    async (kind: string) => (kind === 'stock_inquiry' ? [ROW] : []),
  );
});

describe('PortalLanding - Cards is the default at every width (R3-2, AC-R9)', () => {
  it('defaults to Cards at 375px-equivalent (no match) when nothing is stored', async () => {
    const restore = mockViewportAtLeast768(false);
    try {
      render(<PortalLanding slug="darren" />);
      await screen.findByText('SI-26-0184');

      expect(
        screen.getByRole('radio', { name: 'Board view' }),
      ).toHaveAttribute('aria-checked', 'true');
    } finally {
      restore();
    }
  });

  it('defaults to Cards at 1280px-equivalent (matches) too - the viewport default is gone', async () => {
    const restore = mockViewportAtLeast768(true);
    try {
      render(<PortalLanding slug="darren" />);
      await screen.findByText('SI-26-0184');

      expect(
        screen.getByRole('radio', { name: 'Board view' }),
      ).toHaveAttribute('aria-checked', 'true');
    } finally {
      restore();
    }
  });

  it('a stored choice still wins over the default', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<PortalLanding slug="darren" />);
    await screen.findByText('SI-26-0184');

    expect(
      screen.getByRole('radio', { name: 'List view' }),
    ).toHaveAttribute('aria-checked', 'true');
  });
});

describe('PortalLanding - view persists (AC-L7, unaffected by R3-2)', () => {
  it('persists the pick to localStorage and keeps it across a type switch', async () => {
    render(<PortalLanding slug="darren" />);
    await screen.findByText('SI-26-0184');

    fireEvent.click(screen.getByRole('radio', { name: 'List view' }));
    await waitFor(() =>
      expect(window.localStorage.getItem('sorento.portalView')).toBe('list'),
    );

    // Switch type via the picker, then back - the persisted choice is
    // component state that survives it (D-L4 only resets filter/sort).
    const trigger = screen.getByRole('combobox');
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByText('Purchase Request'));
    await waitFor(() =>
      expect(screen.getByText('New Purchase Request')).toBeInTheDocument(),
    );

    expect(
      screen.getByRole('radio', { name: 'List view' }),
    ).toHaveAttribute('aria-checked', 'true');
  });
});

describe('PortalLanding - List view is a DataGrid table (R3-2, AC-R9)', () => {
  it('renders a table with one column per field of the kind, and the row', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<PortalLanding slug="darren" />);

    const table = await screen.findByRole('table', {}, { timeout: 2000 });
    expect(table).toBeInTheDocument();

    // Column headers: Form Number, Status, the kind's own fields, Created.
    expect(screen.getByRole('columnheader', { name: /Form Number/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Status/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Product/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /Created/ })).toBeInTheDocument();

    expect(screen.getByText('SI-26-0184')).toBeInTheDocument();
  });

  it('clicking a row navigates to the submission detail (rowHref)', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<PortalLanding slug="darren" />);
    await screen.findByRole('table', {}, { timeout: 2000 });

    fireEvent.click(screen.getByText('SI-26-0184'));

    await waitFor(() =>
      expect(push).toHaveBeenCalledWith(
        expect.stringContaining('stock_inquiry/si-1'),
      ),
    );
  });
});
