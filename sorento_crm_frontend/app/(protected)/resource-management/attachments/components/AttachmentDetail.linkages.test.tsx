/**
 * AttachmentDetail Linkages - the Certificates tab.
 *
 * A certification PDF opened from Resource Management had no way back to the
 * register row it created: Linkages listed Products / Promotions / Forms /
 * Packing Lists and nothing else. This pins the fifth tab.
 *
 * What is asserted, and why each one is not incidental:
 * - the tab exists and counts, like its four siblings
 * - View routes to /master-data-management/certificates/<CERTIFICATE id>,
 *     not the revision id (the row carries both; using link_id would 404)
 * - the row is READ-ONLY: no Link, no Unlink. The file is tied to the
 *     certificate by BEING one of its filed revisions, so detaching it here
 *     would leave a revision with no document.
 * - an empty state that says what is actually true of this file
 * - the other four tabs keep their own items
 *
 * Mocks: the metadata fetch and the attachment hooks; everything rendered is
 * the component's own markup.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/resource-management/attachments',
}));

const getAttachmentMetadata = vi.fn();
vi.mock('../services/attachmentService', () => ({
  getAttachmentMetadata: (...args: unknown[]) => getAttachmentMetadata(...args),
}));

// The pager has its own tests (hooks/useListPager.test.ts).
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('../hooks/useAttachments', () => {
  // Defined INSIDE the factory: vi.mock is hoisted above the module body, so a
  // top-level helper would not exist yet when this runs.
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  return {
    useDeleteAttachment: idle,
    useDownloadAttachment: idle,
    useResubmitAttachmentWebhook: idle,
    useRestoreAttachment: idle,
    useUpdateAttachment: idle,
    // Reached through AttachmentDeleteDialog, which the detail always mounts.
    useArchiveAttachment: idle,
    // Pulled in by AttachmentNavigation, which the detail header renders.
    useAttachmentNeighbours: () => ({ data: undefined, isLoading: false }),
    // The pager reads the list page through the entity's shared key + fetch (S3-03).
    attachmentsPagerQuery: {
      listQueryKey: () => ['attachments'],
      fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
    },
  };
});

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [{ code: 'dealer', name: 'Dealer' }] }),
}));

import AttachmentDetail from './AttachmentDetail';

const CERT = {
  id: 'cert-1',
  name: 'PPS WCM PC 000318',
  description: 'WATERMARKS CERTIFICATION - Revision 2',
  link_id: 'revision-9',
};

function attachment(over: Record<string, unknown> = {}) {
  return {
    id: 'att-1',
    original_filename: 'WCM PC 000318 - EXP 13 SEP 2025.pdf',
    stored_filename: 'WCM PC 000318 - EXP 13 SEP 2025.pdf',
    file_path: 'https://cdn.example/cert.pdf',
    file_size_bytes: 1024,
    mime_type: 'application/pdf',
    entity_type: null,
    entity_id: null,
    uploaded_at: '2026-08-06T02:48:00',
    created_at: '2026-08-06T02:48:00',
    is_deleted: false,
    access_levels: ['dealer'],
    linked_products: [],
    linked_promotions: [],
    linked_form: null,
    linked_packing_lists: [],
    linked_certificates: [CERT],
    ...over,
  };
}

function renderDetail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AttachmentDetail attachmentId="att-1" />
    </QueryClientProvider>,
  );
}

/** Radix only mounts the ACTIVE tab panel, so the tab must be opened first. */
async function openCertificatesTab() {
  const tab = await screen.findByRole('tab', { name: /Certificates/ });
  fireEvent.mouseDown(tab);
  fireEvent.click(tab);
  return tab;
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  getAttachmentMetadata.mockResolvedValue(attachment());
});

describe('AttachmentDetail - Certificates linkage tab', () => {
  it('renders the tab with a count, alongside the other four', async () => {
    renderDetail();
    expect(await screen.findByRole('tab', { name: /Certificates \(1\)/ })).toBeInTheDocument();
    for (const label of [/Products/, /Promotions/, /Forms/, /Packing Lists/]) {
      expect(screen.getByRole('tab', { name: label })).toBeInTheDocument();
    }
  });

  it('View routes to the CERTIFICATE, not the revision that carries the file', async () => {
    renderDetail();
    await openCertificatesTab();
    const link = await screen.findByRole('link', { name: /View/ });
    // link_id ('revision-9') is the revision; routing to it would 404.
    expect(link).toHaveAttribute('href', '/master-data-management/certificates/cert-1');
  });

  it('names the certificate and says which revision the file is', async () => {
    renderDetail();
    await openCertificatesTab();
    expect(await screen.findByText('PPS WCM PC 000318')).toBeInTheDocument();
    expect(screen.getByText('WATERMARKS CERTIFICATION - Revision 2')).toBeInTheDocument();
  });

  it('is read-only: no Link and no Unlink', async () => {
    renderDetail();
    const tab = await openCertificatesTab();
    const panel = document.getElementById(tab.getAttribute('aria-controls') || '');
    await waitFor(() => expect(panel).toBeTruthy());
    expect(within(panel as HTMLElement).queryByRole('button', { name: /^Link$/ })).toBeNull();
    expect(within(panel as HTMLElement).queryByRole('button', { name: /Unlink/ })).toBeNull();
  });

  it('an ordinary file gets an empty state that is true of it', async () => {
    getAttachmentMetadata.mockResolvedValue(attachment({ linked_certificates: [] }));
    renderDetail();
    await openCertificatesTab();
    expect(
      await screen.findByText('This file is not filed as a certificate.'),
    ).toBeInTheDocument();
  });

  it('one file filed under two schemes lists both', async () => {
    getAttachmentMetadata.mockResolvedValue(
      attachment({
        linked_certificates: [
          CERT,
          { id: 'cert-2', name: 'SPAN 04124FC', description: 'IKRAM - Revision 1', link_id: 'revision-3' },
        ],
      }),
    );
    renderDetail();
    expect(await screen.findByRole('tab', { name: /Certificates \(2\)/ })).toBeInTheDocument();
    await openCertificatesTab();
    expect(await screen.findByText('PPS WCM PC 000318')).toBeInTheDocument();
    expect(screen.getByText('SPAN 04124FC')).toBeInTheDocument();
  });
});

/**
 * AC-G5 - a shared attachment's Products (and Certificates) rows carry a
 * company badge; the twin the caller has no grant for reads as muted plain
 * text with no View link; a single-company attachment is unchanged (R3, R15,
 * R25, R27). Products defaults open, so these need no tab switch.
 */
describe('AttachmentDetail - shared attachment linkage badges (AC-G5)', () => {
  it('shows a company badge on every row of a shared attachment', async () => {
    getAttachmentMetadata.mockResolvedValue(
      attachment({
        linked_products: [
          { id: 'p-s', name: 'ZZT Valve S', company_id: 'company-s', company_name: 'Sorento', in_scope: true },
          { id: 'p-m', name: 'ZZT Valve M', company_id: 'company-m', company_name: 'Mocha', in_scope: false },
        ],
      }),
    );
    renderDetail();
    expect(await screen.findByText('ZZT Valve S')).toBeInTheDocument();
    expect(screen.getByText('ZZT Valve M')).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
    expect(screen.getByText('Mocha')).toBeInTheDocument();
  });

  it('an out-of-scope row (in_scope=false) is muted plain text with no View link', async () => {
    getAttachmentMetadata.mockResolvedValue(
      attachment({
        linked_products: [
          { id: 'p-s', name: 'ZZT Valve S', company_id: 'company-s', company_name: 'Sorento', in_scope: true },
          { id: 'p-m', name: 'ZZT Valve M', company_id: 'company-m', company_name: 'Mocha', in_scope: false },
        ],
      }),
    );
    renderDetail();
    const outOfScopeName = await screen.findByText('ZZT Valve M');
    expect(outOfScopeName.tagName).not.toBe('A');
    expect(outOfScopeName.className).toMatch(/text-muted-foreground/);
    // The in-scope row keeps its View link; the out-of-scope row has none.
    expect(screen.getAllByRole('link', { name: /View/ })).toHaveLength(1);
  });

  it('a single-company attachment renders with no badges anywhere', async () => {
    getAttachmentMetadata.mockResolvedValue(
      attachment({
        linked_products: [{ id: 'p-1', name: 'ZZT Valve', company_id: null, company_name: null }],
      }),
    );
    renderDetail();
    expect(await screen.findByText('ZZT Valve')).toBeInTheDocument();
    expect(screen.queryByText('Sorento')).not.toBeInTheDocument();
    expect(screen.queryByText('Mocha')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View/ })).toBeInTheDocument();
  });
});
