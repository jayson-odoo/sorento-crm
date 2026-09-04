/**
 * CertificateDetail - tabbed record, warnings only when they fire.
 *   layout (Overview / Products / Revisions tabs, not one long scroll)
 *   FE-5 revised: sections that are ALWAYS relevant (the certificate summary,
 *     coverage, revisions) always render with an empty state. Sections that are
 *     WARNINGS - review flags, unmatched codes, suspected duplicate - render
 *     ONLY when they have something to say. A "Nothing flagged" card is noise.
 *     Reminder history was dropped from the UI entirely.
 *   FE-8 (delete is AlertDialog-confirmed with a count-bearing description and
 *     "This action cannot be undone"; no browser confirm())
 *   FE-9 (header carries the scheme + number title, validity pill, status pill)
 *   loading / not-found / data states
 *
 * The child timeline and covered-products components are rendered for real (not
 * stubbed) so this file proves the SECTION-ALWAYS-RENDERS contract end to end.
 * Their own behaviour is asserted in CertificateRevisionTimeline.test.tsx /
 * CertificateCoveredProducts.test.tsx.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
Element.prototype.scrollIntoView = vi.fn();
// Radix menus probe these; jsdom implements neither.
Element.prototype.hasPointerCapture = vi.fn();
Element.prototype.releasePointerCapture = vi.fn();

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/certificates/cert-1',
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// The Products tab renders a DataGrid, which reads saved column preferences
// through react-query.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), dismiss: vi.fn() },
}));

/* The grace window is the server's; what this file proves is that the gear parks one. */
const createPendingAction = vi.fn().mockResolvedValue({
  id: 'pa-1',
  action_key: 'certificate.delete',
  entity_type: 'certificate',
  entity_id: 'cert-1',
  commit_at: '2026-08-30T10:00:10',
  window_seconds: 10,
});
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: (...args: unknown[]) => createPendingAction(...args),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({
    value,
    onChange,
    options,
    placeholder,
    disabled,
  }: {
    value: string;
    onChange: (v: string) => void;
    options: { value: string; label: string }[];
    placeholder?: string;
    disabled?: boolean;
  }) => (
    <select
      aria-label={placeholder ?? 'select'}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{placeholder ?? ''}</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock('../services/certificateService', () => ({
  getCertificateProductOptions: vi.fn().mockResolvedValue([]),
}));

const hooks = vi.hoisted(() => ({
  useCertificate: vi.fn(),
  useCertificates: vi.fn(),
}));
vi.mock('../hooks/useCertificates', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  certificatesPagerQuery: {
    listQueryKey: () => ['certificates', 'test-page'],
    fetchPage: async () => pagerPage ?? { data: [], pagination: { total: 0 } },
  },
  useCertificate: (...a: unknown[]) => hooks.useCertificate(...a),
  // The detail page pulls an unfiltered page of certificates to feed the
  // prev/next chevrons.
  useCertificates: (...a: unknown[]) => hooks.useCertificates(...a),
  useCertificateMergeTargets: () => ({ data: [], isLoading: false }),
  useMergeCertificate: () => ({ mutate: vi.fn(), isPending: false }),
  useAddCertificateProduct: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRemoveCertificateProduct: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateCertificate: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateCertificate: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import CertificateDetail from './CertificateDetail';
import type { Certificate } from '../types/certificate.types';

/** A certificate with NOTHING attached: no revision, no coverage, no unmatched string, no duplicate. */
function bareCertificate(over: Partial<Certificate> = {}): Certificate {
  return {
    id: 'cert-1',
    scheme: 'PPS',
    certifying_body: 'SIRIM QAS',
    certificate_number: 'PPS 123/2024',
    issuer: null,
    title: null,
    status: 'active',
    validity_state: 'unknown',
    is_expired: false,
    valid_from: null,
    valid_until: null,
    days_until_expiry: null,
    covered_product_count: 0,
    needs_review: false,
    review_reasons: [],
    possible_duplicate_of_certificate_id: null,
    possible_duplicate_of: null,
    current_revision: null,
    revisions: [],
    products: [],
    unmatched_products: [],
    reminders: [],
    created_at: '2024-01-01T00:00:00',
    updated_at: '2024-02-01T00:00:00',
    ...over,
  } as Certificate;
}

/** The list page the pager walks, seeded the way the list leaves it behind. */
let pagerPage: { data: { id: string }[]; pagination: { total: number } } | null = null;

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (pagerPage) client.setQueryData(['certificates', 'test-page'], pagerPage);
  return render(
    <QueryClientProvider client={client}>
      <CertificateDetail certificateId="cert-1" />
    </QueryClientProvider>,
  );
}


/**
 * Move to a tab by its trigger. Radix activates on pointerdown, which jsdom
 * does not synthesize from a click, so fire that explicitly.
 */
function openTab(name: RegExp) {
  const trigger = screen.getByRole('tab', { name });
  fireEvent.pointerDown(trigger, { pointerType: 'mouse', button: 0 });
  fireEvent.mouseDown(trigger, { button: 0 });
  fireEvent.click(trigger);
}

/**
 * Record actions live behind the gear menu, so open it before clicking one.
 * Radix opens on pointerdown, which jsdom does not synthesize from a click, so
 * drive it by keyboard instead (ArrowDown opens and focuses the first item).
 */
function openGearMenu() {
  const trigger = screen.getByRole('button', { name: /Certificate options/i });
  trigger.focus();
  fireEvent.keyDown(trigger, { key: 'ArrowDown', code: 'ArrowDown' });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  // Default: this certificate is the only record, so the counter reads 1 / 1.
  hooks.useCertificates.mockReturnValue({
    data: { data: [{ id: 'cert-1' }], pagination: { total: 1, page: 1, limit: 500 } },
    isLoading: false,
  });
});

describe('CertificateDetail - loading and not-found', () => {
  it('renders skeletons while the certificate loads', () => {
    hooks.useCertificate.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderDetail();
    expect(container.querySelector('[data-slot="skeleton"], .animate-pulse')).toBeTruthy();
  });

  it('renders a not-found state with a way back to the list', () => {
    hooks.useCertificate.mockReturnValue({ data: undefined, isLoading: false });
    renderDetail();
    expect(screen.getByText('Certificate not found')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Back to Certificates/i }));
    expect(push).toHaveBeenCalledWith('/master-data-management/certificates');
  });
});

describe('CertificateDetail - tabs', () => {
  beforeEach(() => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
  });

  it('renders the three tabs, with counts', () => {
    renderDetail();
    expect(screen.getByRole('tab', { name: /Overview/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Products \(0\)/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions \(0\)/i })).toBeInTheDocument();
  });

  it('opens on Overview, showing the certificate summary', () => {
    const { container } = renderDetail();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).toContain('Certificate');
  });

  it('reflects the real counts on the tab labels', () => {
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({
        covered_product_count: 2,
        products: [
          {
            id: 'cov-1',
            product_id: 'p1',
            product_code: 'SR-1',
            product_name: 'One',
            company_name: 'Sorento',
            source: 'ai',
          },
          {
            id: 'cov-2',
            product_id: 'p2',
            product_code: 'SR-2',
            product_name: 'Two',
            company_name: 'Sorento',
            source: 'manual',
          },
        ],
        revisions: [
          {
            id: 'rev-1', revision_no: 1, issued_at: null, valid_from: null, valid_until: null,
            is_current: true, source: 'manual', needs_review: false, review_reasons: [],
            unmatched_products: [], access_levels: [], attachment_filename: null,
            attachment_is_deleted: null, created_at: '2024-01-01T00:00:00',
          },
        ],
      } as Partial<Certificate>),
      isLoading: false,
    });
    renderDetail();
    expect(screen.getByRole('tab', { name: /Products \(2\)/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Revisions \(1\)/i })).toBeInTheDocument();
  });

  it('shows the revision timeline empty state on the Revisions tab', async () => {
    renderDetail();
    openTab(/Revisions/i);
    expect(await screen.findByText('No revision on file')).toBeInTheDocument();
  });

  it('shows the coverage grid empty state on the Products tab', async () => {
    renderDetail();
    openTab(/Products/i);
    expect(
      await screen.findByText(/No product is covered yet\. Use the product picker above/i),
    ).toBeInTheDocument();
  });
});

describe('CertificateDetail - warning sections stay hidden when nothing fired', () => {
  beforeEach(() => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
  });

  it('renders NO review flags card when nothing is flagged', () => {
    const { container } = renderDetail();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).not.toContain('Review flags');
    expect(screen.queryByText('Nothing flagged')).toBeNull();
  });

  it('renders NO unmatched-codes card when everything matched', () => {
    const { container } = renderDetail();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).not.toContain('Unmatched product codes');
    expect(screen.queryByText('Everything matched')).toBeNull();
  });

  it('renders NO suspected-duplicate card when there is no near match', () => {
    const { container } = renderDetail();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).not.toContain('Suspected duplicate');
    expect(screen.queryByText('No near match')).toBeNull();
  });

  it('never renders a reminder history section', () => {
    const { container } = renderDetail();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).not.toContain('Expiry reminders');
  });
});

describe('CertificateDetail - populated sections (FE-5 / FE-9)', () => {
  it('header shows the scheme + number title, validity pill and status pill', () => {
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({ validity_state: 'expired', status: 'archived' }),
      isLoading: false,
    });
    renderDetail();
    expect(screen.getByRole('heading', { name: 'PPS PPS 123/2024' })).toBeInTheDocument();
    expect(screen.getByText('Expired')).toBeInTheDocument();
    expect(screen.getByText('Archived')).toBeInTheDocument();
    // Once in the header sub-line, once as the "Certifying body" summary field.
    expect(screen.getAllByText('SIRIM QAS').length).toBeGreaterThanOrEqual(1);
  });

  it('flags needing review render as labelled reasons with a fix CTA', () => {
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({
        needs_review: true,
        // The real codes the backend emits (certificate_service.REVIEW_*): an
        // object carrying the offending field, plus a bare string to prove the
        // helper still renders a caller that passes a code directly.
        review_reasons: [
          { code: 'missing_required_field', field: 'valid_until' },
          'no_product_coverage',
        ],
      }),
      isLoading: false,
    });
    renderDetail();
    expect(
      screen.getByText('A required field could not be read: valid_until'),
    ).toBeInTheDocument();
    expect(screen.getByText('No product is covered by this certificate')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Fix the details/i })).toBeInTheDocument();
    expect(screen.queryByText('Nothing flagged')).not.toBeInTheDocument();
  });

  it('unmatched strings render as chips with the next-step hint', () => {
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({ unmatched_products: ['SR-9001', 'SR-9002'] }),
      isLoading: false,
    });
    renderDetail();
    expect(screen.getByText('SR-9001')).toBeInTheDocument();
    expect(screen.getByText('SR-9002')).toBeInTheDocument();
    expect(screen.getByText(/Add the matching product under Products/i)).toBeInTheDocument();
    expect(screen.queryByText('Everything matched')).not.toBeInTheDocument();
  });

  it('a suspected duplicate links to the other certificate by its human identity, never an id', () => {
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({
        possible_duplicate_of_certificate_id: 'cert-2',
        possible_duplicate_of: { id: 'cert-2', scheme: 'PPS', certificate_number: 'PPS 122/2021' },
      }),
      isLoading: false,
    });
    renderDetail();
    const link = screen.getByRole('link', { name: /PPS 122\/2021/ });
    expect(link).toHaveAttribute('href', '/master-data-management/certificates/cert-2');
    expect(link.textContent).not.toContain('cert-2');
  });

  it('never renders reminder history, even when the API returns reminders', () => {
    // The backend still records what went out; the detail page just does not
    // show it. Dropping the section must not depend on the payload being empty.
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({
        reminders: [
          { id: 'rem-1', days_before: 30, sent_at: '2026-07-01T09:00:00', recipient_count: 4 },
        ],
      }),
      isLoading: false,
    });
    const { container } = renderDetail();
    expect(screen.queryByText('30 days before expiry')).toBeNull();
    const titles = Array.from(container.querySelectorAll('[data-slot="card-title"]')).map((el) =>
      (el.textContent ?? '').trim(),
    );
    expect(titles).not.toContain('Expiry reminders');
  });
});

describe('CertificateDetail - delete parks a pending action (S6-10)', () => {
  it('parks the delete on the first press, with no dialog in the way', async () => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
    renderDetail();
    openGearMenu();
    fireEvent.click(await screen.findByRole('menuitem', { name: /^Delete certificate$/ }));

    // D7: the press IS the action, and Cancel in the countdown is the way back.
    // What the delete takes with it (revisions, coverage) and what it leaves (the
    // uploaded files) is the server's rule on either path, so it stopped being
    // copy in a dialog nobody could act on.
    await waitFor(() =>
      expect(createPendingAction).toHaveBeenCalledWith(
        expect.objectContaining({
          actionKey: 'certificate.delete',
          entityType: 'certificate',
          entityId: 'cert-1',
        }),
      ),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // Nothing has happened yet, so the page stays where it is until the server says
    // otherwise - a record page that left on the click would be lying for ten seconds.
    expect(push).not.toHaveBeenCalledWith('/master-data-management/certificates');
  });
});

describe('CertificateDetail - Malaysia time (backend sends naive UTC)', () => {
  it('renders Filed and Last updated in Asia/Kuala_Lumpur, not raw UTC', () => {
    // 23:30 UTC is 07:30 the NEXT day in Malaysia, so a formatter that skipped
    // the conversion would print both the wrong hour and the wrong date.
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({
        created_at: '2026-08-03T23:30:00',
        updated_at: '2026-08-03T23:30:00',
      }),
      isLoading: false,
    });
    renderDetail();
    expect(screen.getAllByText('04/08/2026, 7:30 am').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText('03/08/2026, 11:30 pm')).toBeNull();
  });

  it('leaves a DATE-only validity field on its own civil date', () => {
    // valid_until is a DATE column. Converting it through a timezone is how a
    // certificate silently expires a day early or late.
    hooks.useCertificate.mockReturnValue({
      data: bareCertificate({ valid_from: '2026-01-01', valid_until: '2026-12-31' }),
      isLoading: false,
    });
    renderDetail();
    expect(screen.getByText('01/01/2026')).toBeInTheDocument();
    expect(screen.getByText('31/12/2026')).toBeInTheDocument();
  });
});

describe('CertificateDetail - record navigation', () => {
  it('renders the chevrons with the index / total counter between them', () => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
    pagerPage = {
      data: [{ id: 'cert-0' }, { id: 'cert-1' }, { id: 'cert-2' }],
      pagination: { total: 3 },
    };
    renderDetail();
    expect(screen.getByRole('button', { name: /Previous certificate/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next certificate/i })).toBeInTheDocument();
    expect(screen.getByText('2 / 3')).toBeInTheDocument();
  });

  it('routes to the next certificate', () => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
    pagerPage = {
      data: [{ id: 'cert-0' }, { id: 'cert-1' }, { id: 'cert-2' }],
      pagination: { total: 3 },
    };
    renderDetail();
    fireEvent.click(screen.getByRole('button', { name: /Next certificate/i }));
    // The step names the page the record now sits on, so the walk survives it.
    expect(push).toHaveBeenCalledWith(
      '/master-data-management/certificates/cert-2?page=1&limit=50&from=cert-2',
    );
  });

  it('does not crash before the navigation list has loaded', () => {
    hooks.useCertificate.mockReturnValue({ data: bareCertificate(), isLoading: false });
    pagerPage = null;
    renderDetail();
    expect(screen.getByRole('heading', { name: 'PPS PPS 123/2024' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Next certificate/i })).toBeDisabled();
  });
});
