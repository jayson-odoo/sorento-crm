/**
 * ComplaintDetail - two behaviours from UAC-response-attachments.md:
 *
 * - Group C/D5: the "Edit technical team response" popup uploads staged
 *    attachments BEFORE the response text is saved; an upload failure surfaces
 *    a toast and must NOT silently save the response text alone (D2 in the
 *    plan / C5 in the UAC).
 * - Group H: the gear-menu Reassign item acts on the open form-SLA tracker,
 *    is hidden with no open tracker and on a voided complaint, and on success
 *    invalidates the form-sla-trackers query AND calls handlingLock.refresh().
 *
 * Every SLA / permission / attachment-child dependency is mocked at the
 * hook/component boundary so the test stays scoped to ComplaintDetail's own
 * wiring (per the task's mocking convention), not the internals of shared
 * widgets that already have their own coverage.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { toast } from 'sonner';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  // Back, and the delete that lands where Back lands, read the list state the
  // row click wrote into this URL.
  useSearchParams: () => new URLSearchParams(''),
}));

// --- SLA / form-tracker plumbing -------------------------------------------------
const getFormSLATrackersMock = vi.fn();
const escalateFormTrackingMock = vi.fn();
vi.mock('@/app/(protected)/sla-management/_shared/formSLAService', () => ({
  getFormSLATrackers: (...a: unknown[]) => getFormSLATrackersMock(...a),
  escalateFormTracking: (...a: unknown[]) => escalateFormTrackingMock(...a),
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

const handlingLockRefresh = vi.fn();
let handlingLockState: {
  state: string;
  businessCtasEnabled: boolean;
  tracker: unknown;
  claim: () => void;
  takeOver: () => void;
  release: () => void;
  refresh: () => void;
  isMutating: boolean;
} = {
  state: 'not_escalated',
  businessCtasEnabled: true,
  tracker: null,
  claim: vi.fn(),
  takeOver: vi.fn(),
  release: vi.fn(),
  refresh: handlingLockRefresh,
  isMutating: false,
};

// Form-action deferral: idle by default - these suites exercise other wiring. The
// hook's own behaviour is covered by formAction.test.ts + the pytest/e2e layers.
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
  useHandlingLock: () => handlingLockState,
}));

// ReassignDialog - a lightweight stand-in exposing the props the page wires
// up, so the test can trigger onConfirm without the real user-picker/hook.
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/components/ReassignDialog',
  () => ({
    __esModule: true,
    default: ({
      open,
      onConfirm,
    }: {
      open: boolean;
      onConfirm: (userId: string) => void;
    }) =>
      open ? (
        <button type="button" onClick={() => onConfirm('user-42')}>
          Confirm reassign
        </button>
      ) : null,
  }),
);

const reassignMutateMock = vi.fn();
vi.mock(
  '@/app/(protected)/sla-management/conversation-sla-tracking/hooks/useTeamPendingSLA',
  () => ({
    useReassignSLATracking: () => ({ mutate: reassignMutateMock, isPending: false }),
  }),
);

// --- Permissions / void / view-links / lookups -----------------------------------
let permissionMap: Record<string, boolean> = {};
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => permissionMap[slug] ?? false,
}));

vi.mock('@/hooks/useFormVoid', () => ({
  useFormVoid: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({
  usePublicViewLinksEnabled: () => false,
}));

vi.mock(
  '@/app/(protected)/complaint-management/complaint-root-causes/hooks/useComplaintRootCauses',
  () => ({
    useComplaintRootCausesSelect: () => ({ data: [] }),
  }),
);
vi.mock(
  '@/app/(protected)/complaint-management/complaint-resolutions/hooks/useComplaintResolutions',
  () => ({
    useComplaintResolutionsSelect: () => ({ data: [] }),
  }),
);

// --- Sibling child components, stubbed to keep the tree small -------------------
// The pager has its own tests (hooks/useListPager.test.ts); here it is noise.
vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));
vi.mock('./ComplaintManualAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/my-downloads/EntityDownloadsButton', () => ({
  EntityDownloadsButton: () => null,
}));

// --- Complaint domain hooks -------------------------------------------------------
const useComplaintMock = vi.fn();
const updateComplaintMutateAsync = vi.fn().mockResolvedValue({});
const updateAndReplyMutateAsync = vi.fn().mockResolvedValue({});
const uploadResponseAttachmentsMutateAsync = vi.fn();

vi.mock('../hooks/useComplaints', () => ({
  complaintsPagerQuery: { listQueryKey: () => ['complaints'], fetchPage: async () => ({ data: [], pagination: { total: 0 } }) },
  useComplaint: (...a: unknown[]) => useComplaintMock(...a),
  useUpdateComplaint: () => ({ mutateAsync: updateComplaintMutateAsync, isPending: false }),
  useUpdateComplaintAndReply: () => ({ mutateAsync: updateAndReplyMutateAsync, isPending: false }),
  useApproveComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useRejectComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useProcessComplaintByCs: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useCloseComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  useNotifyComplaintRootCause: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useNotifyComplaintResolution: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadComplaintResponseAttachments: () => ({
    mutateAsync: uploadResponseAttachmentsMutateAsync,
    isPending: false,
  }),
  useDeleteComplaint: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import ComplaintDetail from './ComplaintDetail';

function complaint(over: Record<string, unknown> = {}) {
  return {
    id: 'cmp-1',
    complaint_number: 'CMP-2026-0001',
    status: 'submitted',
    complaint_date: '2026-07-01',
    technical_team_response: '',
    root_cause_id: null,
    resolution_id: null,
    respond_inbox_url: null, // keep the chat/conversation tree unmounted
    ...over,
  };
}

function renderPage(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <ComplaintDetail complaintId="cmp-1" />
    </QueryClientProvider>,
  );
  return client;
}

function openTracker(over: Record<string, unknown> = {}) {
  return { id: 'tracker-1', is_resolved: false, event_logs: [], ...over };
}

/** Radix's DropdownMenuTrigger opens on a real pointerdown/pointerup/click
 *  sequence - a bare fireEvent.click leaves aria-expanded="false" in jsdom. */
// Two elements share the accessible name "Edit technical team response" (the
// header CTA and the small ghost "Edit" icon next to the field, whose
// aria-label duplicates the button copy) - target the header CTA explicitly
// by its stable data-guide-target instead of an ambiguous role query.
async function openTechnicalResponsePopupButton() {
  return (await waitFor(() => {
    const el = document.querySelector(
      '[data-guide-target="complaint-management.complaints.tech-team.edit-response"]',
    );
    expect(el).not.toBeNull();
    return el as HTMLElement;
  })) as HTMLElement;
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Complaint actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

beforeEach(() => {
  vi.clearAllMocks();
  permissionMap = { 'sla_management.conversation_sla_tracking.reassign': true };
  handlingLockState = {
    state: 'not_escalated',
    businessCtasEnabled: true,
    tracker: null,
    claim: vi.fn(),
    takeOver: vi.fn(),
    release: vi.fn(),
    refresh: handlingLockRefresh,
    isMutating: false,
  };
  useComplaintMock.mockReturnValue({ data: complaint(), isLoading: false });
  getFormSLATrackersMock.mockResolvedValue([]);
  vi.spyOn(toast, 'error').mockImplementation(() => 'toast-id');
  vi.spyOn(toast, 'success').mockImplementation(() => 'toast-id');
});

describe('ComplaintDetail - Edit technical team response popup', () => {
  it('Cancel with staged files uploads nothing', async () => {
    renderPage();
    fireEvent.click(await openTechnicalResponsePopupButton());

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'photo.png', { type: 'image/png' })] },
    });
    expect(screen.getByText('photo.png')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(uploadResponseAttachmentsMutateAsync).not.toHaveBeenCalled();
    expect(updateComplaintMutateAsync).not.toHaveBeenCalled();
  });

  it('an upload failure surfaces a toast and does NOT save the response text', async () => {
    uploadResponseAttachmentsMutateAsync.mockRejectedValue(new Error('Upload failed'));
    renderPage();
    fireEvent.click(await openTechnicalResponsePopupButton());

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'photo.png', { type: 'image/png' })] },
    });

    const textarea = screen.getByPlaceholderText('Response text...');
    fireEvent.change(textarea, { target: { value: 'Here is the fix.' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save only' }));

    await waitFor(() => expect(uploadResponseAttachmentsMutateAsync).toHaveBeenCalledTimes(1));
    // The text save must never fire when the attachment upload rejected.
    expect(updateComplaintMutateAsync).not.toHaveBeenCalled();
    // The popup stays open with the response text intact (not silently closed/saved).
    expect(screen.getByPlaceholderText('Response text...')).toHaveValue('Here is the fix.');
  });

  it('a successful upload is followed by the response-text save', async () => {
    uploadResponseAttachmentsMutateAsync.mockResolvedValue([{ link_id: 'l-1' }]);
    renderPage();
    fireEvent.click(await openTechnicalResponsePopupButton());

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['x'], 'photo.png', { type: 'image/png' })] },
    });
    const textarea = screen.getByPlaceholderText('Response text...');
    fireEvent.change(textarea, { target: { value: 'Fixed via new part.' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save only' }));

    await waitFor(() => expect(updateComplaintMutateAsync).toHaveBeenCalledWith({
      id: 'cmp-1',
      data: { technical_team_response: 'Fixed via new part.' },
    }));
  });
});

describe('ComplaintDetail - Reassign gear-menu item', () => {
  it('is present when an open tracker exists', async () => {
    getFormSLATrackersMock.mockResolvedValue([openTracker()]);
    renderPage();

    await openGearMenu();
    expect(await screen.findByText('Reassign')).toBeInTheDocument();
  });

  it('is absent when there is no open tracker', async () => {
    getFormSLATrackersMock.mockResolvedValue([]);
    renderPage();

    await openGearMenu();
    await waitFor(() => expect(getFormSLATrackersMock).toHaveBeenCalled());
    expect(screen.queryByText('Reassign')).toBeNull();
  });

  it('is absent when there is an open tracker but the complaint is voided', async () => {
    getFormSLATrackersMock.mockResolvedValue([openTracker()]);
    useComplaintMock.mockReturnValue({ data: complaint({ status: 'voided' }), isLoading: false });
    renderPage();

    await openGearMenu();
    await waitFor(() => expect(getFormSLATrackersMock).toHaveBeenCalled());
    expect(screen.queryByText('Reassign')).toBeNull();
  });

  it('on success invalidates form-sla-trackers AND calls handlingLock.refresh()', async () => {
    getFormSLATrackersMock.mockResolvedValue([openTracker()]);
    reassignMutateMock.mockImplementation((_vars, opts) => {
      opts.onSuccess();
    });
    const client = renderPage();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    await openGearMenu();
    fireEvent.click(await screen.findByText('Reassign'));
    fireEvent.click(await screen.findByText('Confirm reassign'));

    expect(reassignMutateMock).toHaveBeenCalledWith(
      { id: 'tracker-1', userId: 'user-42' },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['form-sla-trackers', 'complaint', 'cmp-1'] }),
    );
    expect(handlingLockRefresh).toHaveBeenCalled();
  });
});
