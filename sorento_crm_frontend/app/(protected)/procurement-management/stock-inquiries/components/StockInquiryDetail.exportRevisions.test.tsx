/**
 * StockInquiryDetail - the "Include revisions" option on the two exports
 * (round 6, 6.4).
 *
 * The question is only asked when it is a real one: the type has revisions
 * switched on AND this record has at least one. Everywhere else both exports
 * behave exactly as they always have, with nothing in the way. When it IS asked,
 * it defaults to yes - someone printing a form that has been revised is normally
 * asking what happened to it.
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
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));

// The revision policy the office reads: one boolean per form type, already
// collapsed server-side.
let revisionEnabledMap: Record<string, boolean> = { stock_inquiry: true };
vi.mock('@/app/(protected)/sla-management/_shared/useRevisionEnabledMap', () => ({
  useRevisionEnabledMap: () => ({ data: revisionEnabledMap }),
}));

const exportToExcel = vi.fn().mockResolvedValue(undefined);
const exportWithRevisions = vi.fn().mockResolvedValue(undefined);
vi.mock('../utils/exportStockInquiryToExcel', () => ({
  exportStockInquiryToExcel: (...a: unknown[]) => exportToExcel(...a),
  exportStockInquiryWithRevisionsToExcel: (...a: unknown[]) => exportWithRevisions(...a),
}));

const useStockInquiryMock = vi.fn();
const exportPdfMutate = vi.fn();
const revisionEntries = [
  { id: 'rev-0', version_no: 0, revision_no: 0, kind: 'original', label: 'Original' },
  { id: 'rev-1', version_no: 1, revision_no: 1, kind: 'revision', label: 'Revision 1' },
];

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
  useExportStockInquiryPdf: () => ({ mutate: exportPdfMutate, isPending: false }),
  useStockInquiryRevisions: () => ({
    data: revisionEntries,
    isLoading: false,
    isError: false,
  }),
}));

import StockInquiryDetail from './StockInquiryDetail';

function inquiry(over: Record<string, unknown> = {}) {
  return {
    id: 'si-1',
    inquiry_number: 'SI-26-0184',
    status: 'pending_purchasing',
    created_at: '2026-07-01T00:00:00Z',
    revision_no: 1,
    purchasing_response: '',
    respond_inbox_url: null,
    attachments: [],
    ...over,
  };
}

function renderPage() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <StockInquiryDetail inquiryId="si-1" />
    </QueryClientProvider>,
  );
}

async function openGearMenu() {
  const trigger = await screen.findByRole('button', { name: 'Stock inquiry actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
}

async function clickMenuItem(name: string) {
  await openGearMenu();
  fireEvent.click(await screen.findByText(name));
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  revisionEnabledMap = { stock_inquiry: true };
  useStockInquiryMock.mockReturnValue({ data: inquiry(), isLoading: false });
});

describe('StockInquiryDetail - include-revisions option', () => {
  it('does not ask when the type has revisions switched off', async () => {
    revisionEnabledMap = { stock_inquiry: false };
    renderPage();
    await clickMenuItem('Export to Excel');

    await waitFor(() => expect(exportToExcel).toHaveBeenCalled());
    expect(screen.queryByTestId('export-include-revisions')).toBeNull();
    expect(exportWithRevisions).not.toHaveBeenCalled();
  });

  it('does not ask when the record has never been revised', async () => {
    useStockInquiryMock.mockReturnValue({ data: inquiry({ revision_no: 0 }), isLoading: false });
    renderPage();
    await clickMenuItem('Export to Excel');

    await waitFor(() => expect(exportToExcel).toHaveBeenCalled());
    expect(screen.queryByTestId('export-include-revisions')).toBeNull();
  });

  it('asks, checked by default, once the record has a revision', async () => {
    renderPage();
    await clickMenuItem('Export to Excel');

    const checkbox = await screen.findByTestId('export-include-revisions');
    expect(checkbox.getAttribute('data-state')).toBe('checked');
    expect(exportToExcel).not.toHaveBeenCalled();
  });

  it('exports the whole lineage when the box stays checked', async () => {
    renderPage();
    await clickMenuItem('Export to Excel');
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(exportWithRevisions).toHaveBeenCalled());
    expect(exportWithRevisions.mock.calls[0]?.[1]).toEqual(revisionEntries);
    expect(exportToExcel).not.toHaveBeenCalled();
  });

  it("exports exactly today's document when the box is unchecked", async () => {
    renderPage();
    await clickMenuItem('Export to Excel');
    fireEvent.click(await screen.findByTestId('export-include-revisions'));
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(exportToExcel).toHaveBeenCalled());
    expect(exportWithRevisions).not.toHaveBeenCalled();
  });

  it('sends include_revisions to the PDF export', async () => {
    renderPage();
    await clickMenuItem('Print / Download PDF');
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(exportPdfMutate).toHaveBeenCalled());
    expect(exportPdfMutate).toHaveBeenCalledWith({
      id: 'si-1',
      options: { include_revisions: true },
    });
  });

  it('sends NO body when the PDF option is unchecked', async () => {
    renderPage();
    await clickMenuItem('Print / Download PDF');
    fireEvent.click(await screen.findByTestId('export-include-revisions'));
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));

    await waitFor(() => expect(exportPdfMutate).toHaveBeenCalled());
    expect(exportPdfMutate).toHaveBeenCalledWith('si-1');
  });

  it('queues the PDF straight away when there is nothing to include', async () => {
    revisionEnabledMap = { stock_inquiry: false };
    renderPage();
    await clickMenuItem('Print / Download PDF');

    await waitFor(() => expect(exportPdfMutate).toHaveBeenCalledWith('si-1'));
  });
});
