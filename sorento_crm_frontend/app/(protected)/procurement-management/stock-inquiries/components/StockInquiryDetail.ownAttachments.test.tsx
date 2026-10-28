/**
 * PORTAL-P4-REQUESTS S-ATT (P4-16, red): the detail page hands the section its own-request kind for a LIMITED user,
 * and not for staff. Scaffolding copied from the requestScope test beside it.
 */
import { submitVerb } from '@/lib/submission-status';
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: async () => [],
  escalateFormTracking: vi.fn(),
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({ SlaActiveTrackerControls: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({
  SlaExtendMenuItem: () => <div role="menuitem">Extend deadline</div>,
  SlaExtendDialog: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({ HandlingLockBanner: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({ HandlingLockReleaseMenuItem: () => null }));
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({ view: { kind: 'idle' }, ctasDisabled: false, cancel: vi.fn(), undo: vi.fn(), refresh: vi.fn(), isMutating: false }),
}));
vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated', businessCtasEnabled: true, tracker: { id: 't1', is_resolved: false, event_logs: [] },
    claim: vi.fn(), takeOver: vi.fn(), release: vi.fn(), refresh: vi.fn(), isMutating: false,
  }),
}));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA', () => ({
  useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false }),
}));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/hooks/useFormVoid', () => ({ useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => true }));
vi.mock('./StockInquiryNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: (p: Record<string, unknown>) => <div data-testid="att-section" data-kind={String(p.requestKind ?? '')} data-readonly={String(!!p.readOnly)} /> }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const inquiryRef: { current: Record<string, unknown> } = { current: {} };
vi.mock('../hooks/useStockInquiries', () => ({
  stockInquiriesPagerQuery: { listQueryKey: () => ['stock-inquiries'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  useStockInquiry: () => ({ data: inquiryRef.current, isLoading: false }),
  useUpdateStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateStockInquiryAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useSubmitStockInquiryForProjectSales: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesApproveStockInquiry: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchasingRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadStockInquiryResponseAttachments: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportStockInquiryPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useStockInquiryRevisions: () => ({ data: [], isLoading: false, isError: false }),
}));

// The revision policy comes from the portal-shaped GET (or from the record itself); both carry the same answer.
const policy = { current: { enabled: true, allowed: false, used: 0, max: 3, remaining: 3, blocked_reason: null } as Record<string, unknown> };
vi.mock('@/lib/api', () => ({
  apiFetch: async (url: string) =>
    new Response(JSON.stringify({ ...inquiryRef.current, revision: policy.current, items: [] }), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    }),
}));

import StockInquiryDetail from './StockInquiryDetail';

// Slugs that light up workflow buttons on the staff page: a limited user holding them still gets none of it.
const WORKFLOW_SLUGS = [
  'procurement.stock_inquiries.submit_for_project_sales',
  'procurement.stock_inquiries.project_sales_approve',
  'procurement.stock_inquiries.project_sales_reject',
  'procurement.stock_inquiries.purchasing_reject',
  'procurement.stock_inquiries.reopen',
  'procurement.stock_inquiries.void',
  'procurement.stock_inquiries.edit',
  'procurement.stock_inquiries.delete',
  'sla_management.conversation_sla_tracking.reassign',
];
const STAFF = ['procurement.stock_inquiries.view', 'procurement.stock_inquiries.edit', 'procurement.stock_inquiries.delete', ...WORKFLOW_SLUGS];
const PORTAL_SET = ['Edit', 'Delete', 'Submit', submitVerb('rejected'), 'Revise', 'Duplicate'];

function record(over: Record<string, unknown> = {}) {
  return {
    id: 'si-1',
    inquiry_number: 'SI-2026-0001',
    status: 'draft',
    created_at: '2026-07-01T00:00:00Z',
    purchasing_response: 'We have stock.',
    respond_inbox_url: 'https://inbox.example/1',
    response_write_allowed: true,
    attachments: [],
    revision_no: 0,
    ...over,
  };
}

function mount(slugs: string[], over: Record<string, unknown> = {}, revisable = false) {
  held = new Set(slugs);
  inquiryRef.current = record(over);
  policy.current = { enabled: true, allowed: revisable, used: 0, max: 3, remaining: 3, blocked_reason: revisable ? null : 'not now' };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('stock inquiry detail passes the attachments section its own-request kind', () => {
  // PORTAL-P4-REQUESTS R1: a limited user now gets the portal's own form; its cases live in StockInquiry.portalForm.test.tsx (its dropzone).

  it('staff: no requestKind', async () => {
    mount(STAFF);
    const el = await screen.findByTestId('att-section');
    expect(el.dataset.kind).toBe('');
  });
});
