/**
 * StockInquiryDetail - the response affordance is removed outside the response
 * stage (UAC O1), while Chat Records stays available at every status (UAC O2).
 *
 * The backend returns 422 for a `purchasing_response` write on a rejected /
 * voided / pre-purchasing inquiry. A button that can only ever toast an error is
 * worse than no button, so it is not rendered at all. What must NOT disappear is
 * the conversation: messaging a contact about a closed record keeps working.
 *
 * The point of these cases is WHERE the decision comes from. It is the server's
 * `response_write_allowed`, not a status list kept on this side: the fixtures
 * below therefore pair an "allowed" flag with a status the old local list called
 * blocked, and vice versa, so a re-introduced mirror list fails them.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  // Back, and the delete that lands where Back lands, read the list state the
  // row click wrote into this URL.
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: vi.fn().mockResolvedValue([]),
  escalateFormTracking: vi.fn(),
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls', () => ({
  SlaActiveTrackerControls: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/SlaExtendAction', () => ({
  SlaExtendMenuItem: () => null,
  SlaExtendDialog: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockBanner', () => ({
  HandlingLockBanner: () => null,
}));
vi.mock('@/app/(protected)/sla-management/_shared/HandlingLockActions', () => ({
  HandlingLockReleaseMenuItem: () => null,
}));
// Form-action deferral plumbing (PLAN-form-sla-undo.md). Mocked exactly as in
// StockInquiryDetail.test.tsx: the real hook reads `useSearchParams`, which this
// file's `next/navigation` mock does not provide, and the response gate under
// test has nothing to do with the undo grace window.
vi.mock('@/app/(protected)/sla-management/_shared/useFormAction', () => ({
  useFormAction: () => ({
    view: { kind: 'idle' },
    ctasDisabled: false,
    cancel: vi.fn(),
    undo: vi.fn(),
    refresh: vi.fn(),
    isMutating: false,
  }),
}));

vi.mock('@/app/(protected)/sla-management/_shared/useHandlingLock', () => ({
  useHandlingLock: () => ({
    state: 'not_escalated',
    businessCtasEnabled: true,
    tracker: null,
    claim: vi.fn(),
    takeOver: vi.fn(),
    release: vi.fn(),
    refresh: vi.fn(),
    isMutating: false,
  }),
}));
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog',
  () => ({ __esModule: true, default: () => null }),
);
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA',
  () => ({ useReassignSLATracking: () => ({ mutate: vi.fn(), isPending: false }) }),
);
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/hooks/useFormVoid', () => ({
  useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({
  usePublicViewLinksEnabled: () => false,
}));
vi.mock('./StockInquiryNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));

const useStockInquiryMock = vi.fn();
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('../hooks/useStockInquiries', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  stockInquiriesPagerQuery: {
    listQueryKey: () => ['stock-inquiries'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useStockInquiry: (...a: unknown[]) => useStockInquiryMock(...a),
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

import StockInquiryDetail from './StockInquiryDetail';

function inquiry(over: Record<string, unknown> = {}) {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    status: 'pending_purchasing',
    created_at: '2026-07-01T00:00:00Z',
    purchasing_response: 'In stock',
    respond_inbox_url: 'https://app.respond.io/space/1/inbox/2',
    revision_no: 0,
    response_write_allowed: true,
    attachments: [],
    ...over,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
}

/** Every affordance that opens the purchasing-response editor: the header CTA
 *  and the inline pencil beside the stored response. */
function responseButtons(): HTMLElement[] {
  return screen.queryAllByRole('button', { name: /Edit purchasing response/ });
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Stock inquiry actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('StockInquiryDetail response gate', () => {
  it('offers the response actions when the server allows the write', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'pending_purchasing', response_write_allowed: true }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
    await openGearMenu();
    expect(screen.getByText('Update & Reply')).toBeInTheDocument();
  });

  it('removes the response actions when the server refuses, keeping Chat records', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'rejected', response_write_allowed: false }),
      isLoading: false,
    });
    renderPage();
    expect(responseButtons()).toHaveLength(0);
    await openGearMenu();
    expect(screen.queryByText('Update & Reply')).not.toBeInTheDocument();
    expect(screen.getByText('Chat records')).toBeInTheDocument();
  });

  it('follows the server flag, not the status - blocked while status reads allowed', async () => {
    // `pending_purchasing` was on the old local allow-list. The flag wins.
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'pending_purchasing', response_write_allowed: false }),
      isLoading: false,
    });
    renderPage();
    expect(responseButtons()).toHaveLength(0);
    await openGearMenu();
    expect(screen.getByText('Chat records')).toBeInTheDocument();
  });

  it('follows the server flag, not the status - allowed while status reads blocked', async () => {
    // `pending_project_sales` was off the old local allow-list. The flag wins.
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'pending_project_sales', response_write_allowed: true }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
  });

  it('treats an absent flag as not gated, matching the backend fail-open', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'rejected', response_write_allowed: undefined }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
  });

  it('renders the suffixed document number in the title once revised', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ revision_no: 3 }),
      isLoading: false,
    });
    renderPage();
    expect(
      await screen.findByRole('heading', { name: /SI-26-0184-R3/ }),
    ).toBeInTheDocument();
  });

  it('renders the bare document number at revision 0', async () => {
    useStockInquiryMock.mockReturnValue({ data: inquiry(), isLoading: false });
    renderPage();
    const heading = await screen.findByRole('heading', { name: /SI-26-0184/ });
    expect(heading.textContent).not.toMatch(/-R\d/);
  });
});
