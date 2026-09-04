/**
 * M5-06 - the Linkages tabs inside AttachmentDetailModal render on DataGrid
 * instead of a raw `<Table>`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { UploadManagerProvider } from '@/components/upload-activity';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/resource-management/attachments',
}));

const getAttachmentMetadata = vi.fn();
vi.mock('../services/attachmentService', () => ({
  getAttachmentMetadata: (...args: unknown[]) => getAttachmentMetadata(...args),
}));

// `idle` is defined INSIDE each factory: vi.mock is hoisted above the module
// body, so a top-level helper would not exist yet when these run.
// The modal always mounts AttachmentDeleteDialog and EditAttachmentTypeDialog
// (closed, but present), which pull in real queries this module also exports
// (useAttachmentTypesList) - importOriginal keeps those working and only
// swaps the mutation hooks the test cares about for idle no-ops.
vi.mock('../hooks/useAttachments', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useAttachments')>();
  const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
  return {
    ...actual,
    useDownloadAttachment: idle,
    useResubmitAttachmentWebhook: idle,
    useRestoreAttachment: idle,
    useUpdateAttachment: idle,
    useDeleteAttachment: idle,
    useArchiveAttachment: idle,
  };
});

vi.mock(
  '@/app/(protected)/master-data-management/product-attachments/hooks/useProductAttachments',
  () => {
    const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
    return {
      useCreateProductAttachment: idle,
      useDeleteProductAttachment: idle,
    };
  },
);

vi.mock(
  '@/app/(protected)/marketing-management/promotion-attachments/hooks/usePromotionAttachments',
  () => {
    const idle = () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false });
    return {
      useCreatePromotionAttachment: idle,
      useDeletePromotionAttachment: idle,
    };
  },
);

vi.mock('@/app/(protected)/forms-management/forms/hooks/useForms', () => ({
  useForms: () => ({ data: { data: [] }, isLoading: false }),
  useUpdateForm: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes', () => ({
  useContactAccessTypes: () => ({ data: [{ code: 'dealer', name: 'Dealer' }] }),
}));

import AttachmentDetailModal from './AttachmentDetailModal';

function attachment(over: Record<string, unknown> = {}) {
  return {
    id: 'att-1',
    original_filename: 'catalogue.pdf',
    stored_filename: 'catalogue.pdf',
    file_path: 'https://cdn.example/catalogue.pdf',
    file_size_bytes: 2048,
    mime_type: 'application/pdf',
    entity_type: null,
    entity_id: null,
    uploaded_at: '2026-08-06T02:48:00',
    created_at: '2026-08-06T02:48:00',
    is_deleted: false,
    access_levels: ['dealer'],
    linked_products: [
      { id: 'p-1', name: 'ZZT Valve A', description: 'Ball valve', link_id: 'link-1' },
      { id: 'p-2', name: 'ZZT Valve B', description: 'Gate valve', link_id: 'link-2' },
    ],
    linked_promotions: [],
    linked_form: null,
    linked_packing_lists: [],
    linked_certificates: [],
    ...over,
  };
}

function renderModal() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <UploadManagerProvider>
        <AttachmentDetailModal open attachmentId="att-1" onOpenChange={vi.fn()} />
      </UploadManagerProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  getAttachmentMetadata.mockResolvedValue(attachment());
});

describe('AttachmentDetailModal - Linkages DataGrid', () => {
  it('renders the Products tab columns and a real cell value for each linked product', async () => {
    renderModal();

    expect(await screen.findByText('ZZT Valve A')).toBeInTheDocument();
    expect(screen.getByText('ZZT Valve B')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
    // "Description" also names the attachment's own description field on
    // this page, so it is not unique - the linkages column header is
    // covered by the row assertions below instead.
    expect(screen.getAllByRole('link', { name: /View/ })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: /Unlink/ })).toHaveLength(2);
  });
});
