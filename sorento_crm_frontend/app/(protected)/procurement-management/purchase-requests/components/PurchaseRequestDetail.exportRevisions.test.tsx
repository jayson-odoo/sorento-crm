/**
 * PurchaseRequestDetail - the "Include revisions" option on the two exports
 * (round 6, 6.4).
 *
 * Same rule as the stock inquiry, with one difference worth pinning: PR and SF
 * are separate types in the revision config, so the flag is read per request
 * type. A sponsorship form must not inherit the purchase request's answer.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  // Back, and the delete that lands where Back lands, read the list state the
  // row click wrote into this URL.
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ settings: {} }) }),
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
vi.mock('@/hooks/useLookupOptionsByBinding', () => ({
  useLookupOptionsByBinding: () => ({ data: undefined, isLoading: false }),
}));
vi.mock('./PurchaseRequestNavigation', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestConversationPanel', () => ({ __esModule: true, default: () => null }));
vi.mock('./PurchaseRequestSignoffFooter', () => ({
  PurchaseRequestSignoffFooter: () => null,
}));
vi.mock('@/components/audit/AuditTrail', () => ({ __esModule: true, default: () => null }));

const getRevisions = vi.fn().mockResolvedValue([]);
vi.mock('../services/purchaseRequestService', () => ({
  sendApprovalLink: vi.fn(),
  setPendingApproval: vi.fn(),
  getUsersForApproverSelect: vi.fn().mockResolvedValue([]),
  getOrCreateViewLink: vi.fn(),
  rejectSubmittedPurchaseRequest: vi.fn(),
  processPurchaseRequestByCs: vi.fn(),
  closePurchaseRequestByCs: vi.fn(),
  submitApprovalDecision: vi.fn(),
  isDeferredDecision: () => false,
  getPurchaseRequestRevisions: (...a: unknown[]) => getRevisions(...a),
}));

let revisionEnabledMap: Record<string, boolean> = { purchase_request: true };
vi.mock('@/app/(protected)/sla-management/_shared/useRevisionEnabledMap', () => ({
  useRevisionEnabledMap: () => ({ data: revisionEnabledMap }),
}));

const exportToExcel = vi.fn().mockResolvedValue(undefined);
const exportWithRevisions = vi.fn().mockResolvedValue(undefined);
vi.mock('../lib/purchase-request-excel-export', () => ({
  exportPurchaseRequestOrSponsorshipToExcel: (...a: unknown[]) => exportToExcel(...a),
  exportPurchaseRequestOrSponsorshipWithRevisionsToExcel: (...a: unknown[]) =>
    exportWithRevisions(...a),
  createSalesTypeLabelResolver: () => () => null,
}));

const usePurchaseRequestMock = vi.fn();
const exportPdfMutate = vi.fn();
const revisionEntries = [
  { id: 'rev-0', version_no: 0, revision_no: 0, kind: 'original', label: 'Original' },
  { id: 'rev-1', version_no: 1, revision_no: 1, kind: 'revision', label: 'Revision 1' },
];

vi.mock('@/components/common/ListPager', () => ({ __esModule: true, default: () => null }));

vi.mock('../hooks/usePurchaseRequests', () => ({
  // The pager reads the list page through the entity's shared key + fetch (S3-03).
  purchaseRequestsPagerQuery: {
    listQueryKey: () => ['purchase-requests'],
    fetchPage: async () => ({ data: [], pagination: { total: 0 } }),
  },
  usePurchaseRequest: (...a: unknown[]) => usePurchaseRequestMock(...a),
  usePurchaseRequestNeighbours: () => ({
    prevId: null,
    nextId: null,
    index: null,
    total: 0,
    isLoading: false,
  }),
  useDeletePurchaseRequestAttachment: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useDeletePurchaseRequest: () => ({ mutateAsync: vi.fn(), isPending: false }),
  usePurchaseRequestConversation: () => ({ data: undefined, isLoading: false }),
  useExportPurchaseRequestPdf: () => ({ mutate: exportPdfMutate, isPending: false }),
  usePurchaseRequestRevisions: () => ({
    data: revisionEntries,
    isLoading: false,
    isError: false,
  }),
}));

import PurchaseRequestDetail from './PurchaseRequestDetail';

function purchaseRequest(over: Record<string, unknown> = {}) {
  return {
    id: 'pr-1',
    request_type: 'purchase_request',
    request_number: 'PR-2026-0001',
    status: 'draft',
    approval_status: null,
    respond_inbox_url: null,
    revision_no: 1,
    updated_at: '2026-07-01T00:00:00Z',
    ...over,
  };
}

function renderPage() {
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <PurchaseRequestDetail requestId="pr-1" />
    </QueryClientProvider>,
  );
}

async function clickMenuItem(name: string) {
  const trigger = await screen.findByRole('button', { name: 'Request actions' });
  fireEvent.pointerDown(trigger, { button: 0, pointerId: 1 });
  fireEvent.pointerUp(trigger, { button: 0, pointerId: 1 });
  fireEvent.click(trigger);
  await waitFor(() => expect(trigger.getAttribute('aria-expanded')).toBe('true'));
  fireEvent.click(await screen.findByText(name));
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  revisionEnabledMap = { purchase_request: true };
  usePurchaseRequestMock.mockReturnValue({ data: purchaseRequest(), isLoading: false });
});

describe('PurchaseRequestDetail - include-revisions option', () => {
  it('does not ask when the type has revisions switched off', async () => {
    revisionEnabledMap = { purchase_request: false, sponsorship_form: true };
    renderPage();
    await clickMenuItem('Export to Excel');

    await waitFor(() => expect(exportToExcel).toHaveBeenCalled());
    expect(screen.queryByTestId('export-include-revisions')).toBeNull();
  });

  it('does not ask when the record has never been revised', async () => {
    usePurchaseRequestMock.mockReturnValue({
      data: purchaseRequest({ revision_no: 0 }),
      isLoading: false,
    });
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

  it('sends include_revisions to the PDF export, and no body when unchecked', async () => {
    renderPage();
    await clickMenuItem('Print / Download PDF');
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));
    await waitFor(() => expect(exportPdfMutate).toHaveBeenCalled());
    expect(exportPdfMutate).toHaveBeenCalledWith({
      id: 'pr-1',
      options: { include_revisions: true },
    });

    cleanup();
    exportPdfMutate.mockClear();
    renderPage();
    await clickMenuItem('Print / Download PDF');
    fireEvent.click(await screen.findByTestId('export-include-revisions'));
    fireEvent.click(await screen.findByRole('button', { name: 'Export' }));
    await waitFor(() => expect(exportPdfMutate).toHaveBeenCalledWith('pr-1'));
  });

  it('reads the flag for the sponsorship form on a sponsorship form', async () => {
    revisionEnabledMap = { purchase_request: false, sponsorship_form: true };
    usePurchaseRequestMock.mockReturnValue({
      data: purchaseRequest({ request_type: 'sponsorship_form' }),
      isLoading: false,
    });
    renderPage();
    await clickMenuItem('Export to Excel');

    expect(await screen.findByTestId('export-include-revisions')).toBeInTheDocument();
    expect(exportToExcel).not.toHaveBeenCalled();
  });
});
