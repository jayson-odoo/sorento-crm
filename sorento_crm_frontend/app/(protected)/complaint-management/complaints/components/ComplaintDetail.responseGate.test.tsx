/**
 * ComplaintDetail - the response affordance is removed outside the response
 * stage (UAC O1), while Chat Records stays available at every status (UAC O2).
 *
 * The backend returns 422 for a `technical_team_response` write on an approved /
 * rejected / processed / closed complaint. A button that can only ever toast an
 * error is worse than no button, so it is not rendered at all. The conversation
 * is untouched: messaging a customer about a closed complaint keeps working
 * exactly as before.
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

vi.mock('next/navigation', () => ({ useRouter: () => ({ push: vi.fn() }) }));

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
// ComplaintDetail.test.tsx: the real hook reads `useSearchParams`, which this
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
vi.mock(
  '@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses',
  () => ({ useComplaintRootCausesSelect: () => ({ data: [] }) }),
);
vi.mock(
  '@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions',
  () => ({ useComplaintResolutionsSelect: () => ({ data: [] }) }),
);
vi.mock('./ComplaintNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => null,
}));

const useComplaintMock = vi.fn();
vi.mock('../hooks/useComplaints', () => ({
  useComplaint: (...a: unknown[]) => useComplaintMock(...a),
  useUpdateComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateComplaintAndReply: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useApproveComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRejectComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProcessComplaintByCs: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCloseComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useNotifyComplaintRootCause: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useNotifyComplaintResolution: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadComplaintResponseAttachments: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeleteComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import ComplaintDetail from './ComplaintDetail';

function complaint(over: Record<string, unknown> = {}) {
  return {
    id: 'cmp-1',
    complaint_number: 'CMP-2026-0001',
    status: 'submitted',
    complaint_date: '2026-07-01',
    technical_team_response: 'Coil replaced',
    root_cause_id: null,
    resolution_id: null,
    respond_inbox_url: 'https://app.respond.io/space/1/inbox/2',
    response_write_allowed: true,
    ...over,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cmp-1" />
    </QueryClientProvider>,
  );
}

/** Every affordance that opens the technical-response editor: the header CTA
 *  and the inline pencil beside the stored response. */
function responseButtons(): HTMLElement[] {
  return screen.queryAllByRole('button', { name: /Edit technical team response/ });
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Complaint actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ComplaintDetail response gate', () => {
  it('offers the response actions when the server allows the write', async () => {
    useComplaintMock.mockReturnValue({
      data: complaint({ status: 'submitted', response_write_allowed: true }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
    await openGearMenu();
    expect(screen.getByText('Update & Reply')).toBeInTheDocument();
  });

  it.each(['approved', 'rejected', 'processed_by_cs', 'closed'])(
    'removes the response actions when the server refuses at %s, keeping Chat records',
    async (status) => {
      useComplaintMock.mockReturnValue({
        data: complaint({ status, response_write_allowed: false }),
        isLoading: false,
      });
      renderPage();
      expect(responseButtons()).toHaveLength(0);
      await openGearMenu();
      expect(screen.queryByText('Update & Reply')).not.toBeInTheDocument();
      expect(screen.getByText('Chat records')).toBeInTheDocument();
    },
  );

  it('follows the server flag, not the status - blocked while status reads allowed', async () => {
    // `responded` was on the old local allow-list. The flag wins.
    useComplaintMock.mockReturnValue({
      data: complaint({ status: 'responded', response_write_allowed: false }),
      isLoading: false,
    });
    renderPage();
    expect(responseButtons()).toHaveLength(0);
    await openGearMenu();
    expect(screen.getByText('Chat records')).toBeInTheDocument();
  });

  it('follows the server flag, not the status - allowed while status reads blocked', async () => {
    // `closed` was off the old local allow-list. The flag wins.
    useComplaintMock.mockReturnValue({
      data: complaint({ status: 'closed', response_write_allowed: true }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
  });

  it('treats an absent flag as not gated, matching the backend fail-open', async () => {
    useComplaintMock.mockReturnValue({
      data: complaint({ status: 'closed', response_write_allowed: undefined }),
      isLoading: false,
    });
    renderPage();
    await waitFor(() => expect(responseButtons()).not.toHaveLength(0));
  });
});
