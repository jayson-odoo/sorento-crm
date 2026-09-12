/**
 * PLAN-portal-price-tag-journey-r8, D-L5 (AC-L7): the card/list view toggle.
 *
 * Default board under 768px, list at 768px and up when nothing is stored;
 * the choice persists per device (`localStorage['sorento.portalView']`) and
 * survives a type switch; list view renders exactly one line per submission,
 * every cell truncated with a `title`.
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

/** `window.matchMedia('(min-width: 768px)')` - the one query PortalLanding
 *  reads to pick a first-visit default. Everything else keeps the suite's
 *  own default ("no match" - see `vitest.setup.ts`). */
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

describe('PortalLanding - view default (AC-L7)', () => {
  it('defaults to board under 768px when nothing is stored', async () => {
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

  it('defaults to list at 768px and up when nothing is stored', async () => {
    const restore = mockViewportAtLeast768(true);
    try {
      render(<PortalLanding slug="darren" />);
      await screen.findByText('SI-26-0184');

      expect(
        screen.getByRole('radio', { name: 'List view' }),
      ).toHaveAttribute('aria-checked', 'true');
    } finally {
      restore();
    }
  });

  it('a stored choice wins over the viewport default', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    const restore = mockViewportAtLeast768(false);
    try {
      render(<PortalLanding slug="darren" />);
      await screen.findByText('SI-26-0184');

      expect(
        screen.getByRole('radio', { name: 'List view' }),
      ).toHaveAttribute('aria-checked', 'true');
    } finally {
      restore();
    }
  });
});

describe('PortalLanding - view persists (AC-L7)', () => {
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

describe('PortalLanding - list view rows (AC-L7)', () => {
  it('renders exactly one line per submission, with truncate + title on the long cell', async () => {
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<PortalLanding slug="darren" />);

    const cell = await screen.findByTitle(ROW.product_code!);
    expect(cell).toHaveClass('truncate');
    expect(cell.tagName).toBe('SPAN');
    // The row itself is a single flex line, not a stacked card - no
    // block-level wrapper holding a second row of content underneath it.
    const rowEl = cell.closest('[role="link"]');
    expect(rowEl).toHaveClass('items-center');
    expect(rowEl?.querySelectorAll(':scope > div')).toHaveLength(0);
  });

  it('formats needed_by_date like the created date (toLocaleDateString), not raw ISO (review round 2)', async () => {
    (fetchSubmissions as ReturnType<typeof vi.fn>).mockImplementation(
      async (kind: string) =>
        kind === 'stock_inquiry' ? [{ ...ROW, needed_by_date: '2026-09-15' }] : [],
    );
    window.localStorage.setItem('sorento.portalView', 'list');
    render(<PortalLanding slug="darren" />);
    await screen.findByText('SI-26-0184');

    const expected = new Date('2026-09-15').toLocaleDateString(undefined, {
      dateStyle: 'medium',
    });
    expect(screen.getByTitle(expected)).toBeInTheDocument();
    expect(screen.queryByTitle('2026-09-15')).toBeNull();
    expect(screen.queryByText('2026-09-15')).toBeNull();
  });
});
