/**
 * PORTAL-P4-REQUESTS S-ATT: the staff Purchase Request / Sponsorship attachments section, unchanged.
 * Never calls myRequestsService. A salesperson's own files live inside the portal's form since R2
 * (form parity), so the section has no own-request mode (PurchaseRequest.portalForm.test.tsx).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Sam Sales' } }, status: 'authenticated' }),
}));
vi.mock('@/components/common/deferredToast', () => ({
  deferredToast: vi.fn(() => 'toast-1'),
  dismissDeferredToast: vi.fn(),
}));
const pending = vi.hoisted(() => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));
vi.mock('@/services/pendingActionService', () => pending);

const noopMutation = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/usePurchaseRequests', () => ({
  useDeletePurchaseRequestAttachment: () => noopMutation,
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

import PurchaseRequestAttachmentsSection from './PurchaseRequestAttachmentsSection';

const ROW = (over: Record<string, unknown>) => ({
  request_id: 'pr-1',
  file_url: 'https://cdn.example.com/x.pdf',
  file_size_bytes: 1024,
  uploaded_at: '2026-01-05T00:00:00',
  
  ...over,
});
const STAFF_FILE = ROW({ id: 'link-staff', attachment_id: 'att-staff', file_name: 'staff-reply.pdf', original_filename: 'staff-reply.pdf', uploaded_by_name: 'Alice Tan', uploaded_by_role: 'staff', uploader_kind: 'user' });
const OWN_FILE = ROW({ id: 'link-own', attachment_id: 'att-own', file_name: 'my-photo.pdf', original_filename: 'my-photo.pdf', uploaded_by_name: 'Sam Sales', uploaded_by_role: 'contact', uploader_kind: 'contact' });

function mount(props: Record<string, unknown> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PurchaseRequestAttachmentsSection requestId="pr-1" attachments={[STAFF_FILE, OWN_FILE] as never} {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  svc.uploadAttachment.mockResolvedValue({ link_id: 'l-new', attachment_id: 'a-new', filename: 'new.pdf', size: 3, url: 'u', content_type: 'application/pdf' });
  svc.deleteAttachment.mockResolvedValue(undefined);
  pending.getCurrentPendingAction.mockResolvedValue({ pending: null, last_outcome: null });
  pending.cancelPendingAction.mockResolvedValue(undefined);
  pending.createPendingAction.mockResolvedValue({
    id: 'pa-1',
    action_key: 'my_request_attachment.unlink',
    entity_type: 'my_request_attachment',
    entity_id: 'link-own',
    commit_at: new Date(Date.now() + 5_000).toISOString().replace(/\.\d+Z$/, ''),
    window_seconds: 5,
  });
});

describe('PurchaseRequestAttachmentsSection, staff (no requestKind): unchanged', () => {
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
