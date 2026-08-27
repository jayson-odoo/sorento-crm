/**
 * AttachmentDetail - the owning company on the details card.
 *
 * A file uploaded into the root folder used to land with no company on it, so
 * the card gave the user no way to tell whose file they were looking at. The
 * backend now stamps company_id/company_name on the metadata read, and this
 * pins the two readings that matter:
 * - a stamped file names its company
 * - a file with NO company (company_id null) is visible to every company, and
 *     says so as "Shared" rather than showing a blank or a raw id
 *
 * Mocks mirror AttachmentDetail.linkages.test.tsx: the metadata fetch and the
 * attachment hooks; everything asserted is the component's own markup.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
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
    useArchiveAttachment: idle,
    useAttachmentNeighbours: () => ({ data: undefined, isLoading: false }),
  };
});

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [{ code: 'dealer', name: 'Dealer' }] }),
}));

import AttachmentDetail from './AttachmentDetail';

function attachment(over: Record<string, unknown> = {}) {
  return {
    id: 'att-1',
    original_filename: 'price-list.pdf',
    stored_filename: 'price-list.pdf',
    file_path: 'https://cdn.example/price-list.pdf',
    file_size_bytes: 1024,
    mime_type: 'application/pdf',
    entity_type: null,
    entity_id: null,
    uploaded_at: '2026-08-27T02:48:00',
    created_at: '2026-08-27T02:48:00',
    is_deleted: false,
    access_levels: ['dealer'],
    linked_products: [],
    linked_promotions: [],
    linked_form: null,
    linked_packing_lists: [],
    linked_certificates: [],
    company_id: 'company-1',
    company_name: 'Sorento',
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

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  getAttachmentMetadata.mockResolvedValue(attachment());
});

describe('AttachmentDetail - owning company', () => {
  it('names the company that owns the file', async () => {
    renderDetail();
    expect(await screen.findByText('Company')).toBeInTheDocument();
    expect(screen.getByText('Sorento')).toBeInTheDocument();
  });

  it('a file with no company reads as Shared, not blank and not an id', async () => {
    getAttachmentMetadata.mockResolvedValue(
      attachment({ company_id: null, company_name: null }),
    );
    renderDetail();
    expect(await screen.findByText('Company')).toBeInTheDocument();
    expect(screen.getByText('Shared')).toBeInTheDocument();
  });
});
