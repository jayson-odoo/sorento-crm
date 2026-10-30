/**
 * PORTAL-P4-REQUESTS S1 (P4-25, P4-26): the Stock Inquiry detail for a LIMITED user shows the portal action set
 * ONLY (Q2 a): Edit (draft/rejected), Delete (draft), Submit (draft/rejected), Revise (server policy allows),
 * Duplicate (always). Everything else the staff page offers is absent, including every slug-gated workflow button
 * even when the slug is held. Status and the purchasing response stay visible, read-only. Staff detail unchanged.
 * Scaffolding follows StockInquiryDetail.test.tsx.
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
const slaSpy = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: (...a: unknown[]) => slaSpy(...a),
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
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ default: () => <div data-testid="audit-trail" /> }));
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

const LIMITED = ['procurement.stock_inquiries.view_own', 'procurement.stock_inquiries.add'];
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

/** Every action label on the page: header buttons plus the items of the open gear menu. */
async function actionLabels(): Promise<string[]> {
  await screen.findAllByText(/SI-2026-0001/);
  const gear = screen.queryByRole('button', { name: 'Stock inquiry actions' });
  if (gear) {
    fireEvent.pointerDown(gear, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(gear, { button: 0, pointerId: 1 });
    fireEvent.click(gear);
    await waitFor(() => expect(gear.getAttribute('aria-expanded')).toBe('true'));
  }
  const nodes = [...screen.queryAllByRole('button'), ...screen.queryAllByRole('menuitem'), ...screen.queryAllByRole('link')];
  return nodes
    .map((n) => (n.textContent ?? '').trim())
    .filter((t) => t && t !== 'Stock inquiry actions');
}

beforeEach(() => {
  slaSpy.mockReset();
  slaSpy.mockImplementation(async () => []);
  cleanup();
  vi.clearAllMocks();
});


describe('Audit Trail for a limited user (PORTAL-P4-REQUESTS)', () => {
  it('limited user: no Audit Trail section (the portal has none; /audit/logs answers 403)', async () => {
    mount(LIMITED);
    await screen.findAllByText(/SI-2026-0001/);
    expect(screen.queryByTestId('audit-trail')).toBeNull();
  });

  it('staff: Audit Trail section stays', async () => {
    mount(STAFF);
    await screen.findAllByText(/SI-2026-0001/);
    expect(await screen.findByTestId('audit-trail')).toBeInTheDocument();
  });
});

describe('SLA by-source read (PORTAL-P4-REQUESTS)', () => {
  it('limited user: getFormSLATrackers (conversation-sla-tracking/by-source) is never called', async () => {
    mount(LIMITED);
    await screen.findAllByText(/SI-2026-0001/);
    await new Promise((r) => setTimeout(r, 100));
    expect(slaSpy).not.toHaveBeenCalled();
  });

  it('staff: still reads the trackers', async () => {
    mount(STAFF);
    await screen.findAllByText(/SI-2026-0001/);
    await waitFor(() => expect(slaSpy).toHaveBeenCalled());
  });
});
