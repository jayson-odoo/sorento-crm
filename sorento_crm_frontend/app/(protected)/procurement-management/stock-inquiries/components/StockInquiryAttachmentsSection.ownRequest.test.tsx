/**
 * PORTAL-P4-REQUESTS S-ATT (P4-16, red): Stock Inquiry attachments for a salesperson.
 *
 * Contract (new optional prop, absent = today's staff behaviour, unchanged):
 *   <StockInquiryAttachmentsSection inquiryId="..." attachments={...} requestKind="stock_inquiry" />
 * `requestKind` puts the section in own-request mode:
 *   - a file input uploads through myRequestsService.uploadAttachment(kind, id, file);
 *   - a delete action (accessible name /delete|remove/i, not "Unlink") shows ONLY on rows whose
 *     uploaded_by_role is 'contact' and calls myRequestsService.deleteAttachment(link.id);
 *   - staff rows (uploaded_by_role 'staff') carry no delete;
 *   - download links use myRequestsAttachmentDownloadUrl(attachment_id), not the resource-management route;
 *   - no "Link Attachment" and no "Unlink" (those are staff-only).
 * Without requestKind the staff UI is untouched and never calls myRequestsService.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useStockInquiries', () => ({
  useDeleteStockInquiryAttachment: () => noopMutation,
  useDeleteStockInquiryResponseAttachment: () => noopMutation,
}));

const svc = vi.hoisted(() => ({
  uploadAttachment: vi.fn(),
  deleteAttachment: vi.fn(),
}));
vi.mock('@/services/myRequestsService', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  uploadAttachment: svc.uploadAttachment,
  deleteAttachment: svc.deleteAttachment,
}));

import StockInquiryAttachmentsSection from './StockInquiryAttachmentsSection';

const ROW = (over: Record<string, unknown>) => ({
  inquiry_id: 'si-1',
  file_url: 'https://cdn.example.com/x.pdf',
  file_size_bytes: 1024,
  uploaded_at: '2026-01-05T00:00:00',
  link_type: 'stock_inquiry_attachment' as const,
  ...over,
});
const STAFF_FILE = ROW({ id: 'link-staff', attachment_id: 'att-staff', file_name: 'staff-reply.pdf', original_filename: 'staff-reply.pdf', uploaded_by_name: 'Alice Tan', uploaded_by_role: 'staff', uploader_kind: 'user' });
const OWN_FILE = ROW({ id: 'link-own', attachment_id: 'att-own', file_name: 'my-photo.pdf', original_filename: 'my-photo.pdf', uploaded_by_name: 'Sam Sales', uploaded_by_role: 'contact', uploader_kind: 'contact' });

function mount(props: Record<string, unknown> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StockInquiryAttachmentsSection inquiryId="si-1" attachments={[STAFF_FILE, OWN_FILE] as never} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  svc.uploadAttachment.mockResolvedValue({ link_id: 'l-new', attachment_id: 'a-new', filename: 'new.pdf', size: 3, url: 'u', content_type: 'application/pdf' });
  svc.deleteAttachment.mockResolvedValue(undefined);
});

describe('StockInquiryAttachmentsSection, salesperson (requestKind="stock_inquiry")', () => {
  it('a file input uploads through myRequestsService.uploadAttachment', async () => {
    const { container } = mount({ requestKind: 'stock_inquiry' });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement | null;
    expect(input, 'no file input for the salesperson').not.toBeNull();
    const file = new File(['%PDF'], 'new.pdf', { type: 'application/pdf' });
    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });
    await waitFor(() => expect(svc.uploadAttachment).toHaveBeenCalledWith('stock_inquiry', 'si-1', file));
  });

  it('own file shows a delete action that calls my-requests DELETE with the link id', async () => {
    mount({ requestKind: 'stock_inquiry' });
    const row = screen.getByText('my-photo.pdf').closest('tr') as HTMLElement;
    fireEvent.click(within(row).getByRole('button', { name: /delete|remove/i }));
    const dialog = screen.queryByRole('alertdialog');
    if (dialog) fireEvent.click(within(dialog).getByRole('button', { name: /delete|remove|confirm/i }));
    await waitFor(() => expect(svc.deleteAttachment).toHaveBeenCalledWith('link-own'));
  });

  it('a staff-uploaded file shows no delete or unlink for them', () => {
    mount({ requestKind: 'stock_inquiry' });
    const row = screen.getByText('staff-reply.pdf').closest('tr') as HTMLElement;
    expect(within(row).queryByRole('button', { name: /delete|remove|unlink/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /link attachment/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /unlink/i })).toBeNull();
  });

  it('download uses myRequestsAttachmentDownloadUrl, not the staff resource route', () => {
    mount({ requestKind: 'stock_inquiry' });
    const hrefs = screen.getAllByRole('link', { name: /download/i }).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/api/v1/my-requests/attachments/att-own/download');
    expect(hrefs).toContain('/api/v1/my-requests/attachments/att-staff/download');
    expect(hrefs.filter((h) => h?.includes('resource-management'))).toEqual([]);
  });
});

describe('StockInquiryAttachmentsSection, staff (no requestKind): unchanged', () => {
  it('keeps Link Attachment and Unlink, offers no upload, never calls my-requests', () => {
    const { container } = mount();
    expect(screen.getByRole('button', { name: /link attachment/i })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /unlink/i })).toHaveLength(2);
    expect(container.querySelector('input[type="file"]')).toBeNull();
    const hrefs = screen.getAllByRole('link', { name: /download/i }).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/api/v1/resource-management/attachments/att-own/download');
    expect(svc.uploadAttachment).not.toHaveBeenCalled();
    expect(svc.deleteAttachment).not.toHaveBeenCalled();
  });
});
