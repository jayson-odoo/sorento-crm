/**
 * PORTAL-P4-REQUESTS review fix (red): a limited user's Download in the own-request attachment
 * sections must go through apiFetch (so X-Impersonate-User-Id rides along) and save with saveBlobAs.
 * A plain <a href="/api/v1/my-requests/attachments/{id}/download"> sends no impersonation header.
 * Covers the SI, PR and Complaint sections plus the my-requests service helper.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const noop = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useStockInquiries', () => ({
  useDeleteStockInquiryAttachment: () => noop,
  useDeleteStockInquiryResponseAttachment: () => noop,
}));
vi.mock('@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests', () => ({
  useDeletePurchaseRequestAttachment: () => noop,
}));
vi.mock('@/app/(protected)/complaint-management/complaints/hooks/useComplaints', () => ({
  useDeleteComplaintAttachment: () => noop,
  useDeleteComplaintResponseAttachment: () => noop,
}));

const h = vi.hoisted(() => ({ apiFetch: vi.fn(), saveBlobAs: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: unknown[]) => h.apiFetch(...a),
}));
vi.mock('@/lib/save-blob', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  saveBlobAs: (...a: unknown[]) => h.saveBlobAs(...a),
}));

import StockInquiryAttachmentsSection from './StockInquiryAttachmentsSection';
import PurchaseRequestAttachmentsSection from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestAttachmentsSection';
import ComplaintManualAttachmentsSection from '@/app/(protected)/complaint-management/complaints/components/ComplaintManualAttachmentsSection';

const ROW = (over: Record<string, unknown>) => ({
  inquiry_id: 'x-1',
  request_id: 'x-1',
  complaint_id: 'x-1',
  file_url: 'https://cdn.example.com/x.pdf',
  file_size_bytes: 1024,
  uploaded_at: '2026-01-05T00:00:00',
  link_type: 'attachment',
  id: 'link-own',
  attachment_id: 'att-own',
  file_name: 'my-photo.pdf',
  original_filename: 'my-photo.pdf',
  uploaded_by_name: 'Sam Sales',
  uploaded_by_role: 'contact',
  uploader_kind: 'contact',
  ...over,
});

const CASES: Array<[string, string, (a: unknown[]) => React.ReactElement]> = [
  ['stock_inquiry', 'StockInquiryAttachmentsSection', (a) => <StockInquiryAttachmentsSection inquiryId="x-1" attachments={a as never} requestKind="stock_inquiry" />],
  ['purchase_request', 'PurchaseRequestAttachmentsSection', (a) => <PurchaseRequestAttachmentsSection requestId="x-1" attachments={a as never} requestKind="purchase_request" />],
  ['complaint', 'ComplaintManualAttachmentsSection', (a) => <ComplaintManualAttachmentsSection complaintId="x-1" attachments={a as never} requestKind="complaint" />],
];

function mount(el: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}>{el}</QueryClientProvider>);
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  h.apiFetch.mockImplementation(async () => new Response('%PDF', { status: 200 }));
});

describe.each(CASES)('%s own-request Download (%s)', (_kind, _name, build) => {
  it('has no plain href to the my-requests download route', () => {
    const { container } = mount(build([ROW({})]));
    const hrefs = Array.from(container.querySelectorAll('a[href]')).map((a) => a.getAttribute('href'));
    expect(hrefs.filter((h2) => h2?.includes('/my-requests/attachments/'))).toEqual([]);
  });

  it('clicking Download fetches through apiFetch and saves with saveBlobAs', async () => {
    mount(build([ROW({})]));
    fireEvent.click(screen.getByText('Download'));
    await waitFor(() =>
      expect(h.apiFetch.mock.calls.map((c) => String(c[0]))).toContain('/api/v1/my-requests/attachments/att-own/download'),
    );
    await waitFor(() => expect(h.saveBlobAs).toHaveBeenCalledTimes(1));
    expect(h.saveBlobAs.mock.calls[0][1]).toBe('my-photo.pdf');
  });
});
