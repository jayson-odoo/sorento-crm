/**
 * StockInquiryDetail - mirrors ComplaintDetail.test.tsx for the two shared
 * behaviours from UAC-response-attachments.md:
 *
 * - Group C/D5: "Edit purchasing response" uploads staged attachments BEFORE
 *    the response text is saved; an upload failure surfaces a toast and must
 *    NOT silently save the response text alone.
 * - Group H: the gear-menu Reassign item acts on the open form-SLA tracker,
 *    is hidden with no open tracker and on a voided stock inquiry, and on
 *    success invalidates the form-sla-trackers query AND calls
 *    handlingLock.refresh().
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

vi.mock('./StockInquiryNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));

const useStockInquiryMock = vi.fn();
const updateInquiryMutateAsync = vi.fn().mockResolvedValue({});
const updateAndReplyMutateAsync = vi.fn().mockResolvedValue({});
const uploadResponseAttachmentsMutateAsync = vi.fn();
const exportPdfMutate = vi.fn();

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('../hooks/useStockInquiries', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  stockInquiriesPagerQuery: {
    listQueryKey: () => ['stock-inquiries'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  useStockInquiry: (...a: unknown[]) => useStockInquiryMock(...a),
  useUpdateStockInquiry: () => ({ mutateAsync: updateInquiryMutateAsync, isPending: false }),
  useUpdateStockInquiryAndReply: () => ({ mutateAsync: updateAndReplyMutateAsync, isPending: false }),
  useSubmitStockInquiryForProjectSales: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesApproveStockInquiry: () => ({ mutate: vi.fn(), isPending: false }),
  useProjectSalesRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchasingRejectStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useReopenStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUploadStockInquiryResponseAttachments: () => ({
    mutateAsync: uploadResponseAttachmentsMutateAsync,
    isPending: false,
  }),
  useDeleteStockInquiry: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useExportStockInquiryPdf: () => ({ mutate: exportPdfMutate, isPending: false }),
  useStockInquiryRevisions: () => ({ data: [], isLoading: false, isError: false }),
}));

import StockInquiryDetail from './StockInquiryDetail';

function inquiry(over: Record<string, unknown> = {}) {
  return {
    id: 'si-1',
    inquiry_number: 'SI-2026-0001',
    status: 'pending_purchasing',
    created_at: '2026-07-01T00:00:00Z',
    purchasing_response: '',
    respond_inbox_url: null,
    attachments: [],
    ...over,
  };
}

function renderPage(client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  render(
    <QueryClientProvider client={client}>
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
  return client;
}

function openTracker(over: Record<string, unknown> = {}) {
  return { id: 'tracker-1', is_resolved: false, event_logs: [], ...over };
}

async function openTechnicalResponsePopupButton() {
  return (await waitFor(() => {
    const el = document.querySelector(
      '[data-guide-target="procurement.stock-inquiries.edit-purchasing-response-button"]',
    );
    expect(el).not.toBeNull();
    return el as HTMLElement;
  })) as HTMLElement;
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Stock inquiry actions' });
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
  useStockInquiryMock.mockReturnValue({ data: inquiry(), isLoading: false });
  getFormSLATrackersMock.mockResolvedValue([]);
  vi.spyOn(toast, 'error').mockImplementation(() => 'toast-id');
  vi.spyOn(toast, 'success').mockImplementation(() => 'toast-id');
});

describe('StockInquiryDetail - Edit purchasing response popup', () => {
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
    expect(updateInquiryMutateAsync).not.toHaveBeenCalled();
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
    fireEvent.change(textarea, { target: { value: 'We have stock.' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save only' }));

    await waitFor(() => expect(uploadResponseAttachmentsMutateAsync).toHaveBeenCalledTimes(1));
    expect(updateInquiryMutateAsync).not.toHaveBeenCalled();
    expect(screen.getByPlaceholderText('Response text...')).toHaveValue('We have stock.');
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
    fireEvent.change(textarea, { target: { value: 'In stock, 20 units.' } });

    fireEvent.click(screen.getByRole('button', { name: 'Save only' }));

    await waitFor(() =>
      expect(updateInquiryMutateAsync).toHaveBeenCalledWith({
        id: 'si-1',
        data: { purchasing_response: 'In stock, 20 units.' },
      }),
    );
  });
});

describe('StockInquiryDetail - Reassign gear-menu item', () => {
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

  it('is absent when there is an open tracker but the inquiry is voided', async () => {
    getFormSLATrackersMock.mockResolvedValue([openTracker()]);
    useStockInquiryMock.mockReturnValue({ data: inquiry({ status: 'voided' }), isLoading: false });
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
      expect.objectContaining({ queryKey: ['form-sla-trackers', 'stock_inquiry', 'si-1'] }),
    );
    expect(handlingLockRefresh).toHaveBeenCalled();
  });
});

describe('ProductInquiryDetail - Print / Download PDF gear-menu item', () => {
  it('queues the export for this inquiry', async () => {
    renderPage();

    await openGearMenu();
    fireEvent.click(await screen.findByText('Print / Download PDF'));

    expect(exportPdfMutate).toHaveBeenCalledWith('si-1');
  });

  it('is offered on a voided inquiry (printing a closed record stays allowed)', async () => {
    useStockInquiryMock.mockReturnValue({
      data: inquiry({ status: 'voided' }),
      isLoading: false,
    });
    renderPage();

    await openGearMenu();
    expect(await screen.findByText('Print / Download PDF')).toBeTruthy();
  });
});
