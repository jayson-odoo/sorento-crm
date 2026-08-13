/**
 * FormRevisionsTab - the body of the office Revisions tab (round 6, UAC H2).
 *
 * Covers: kind routes to exactly one backend lineage (stock inquiry vs the
 * shared purchase-request/sponsorship-form route), the lineage query is keyed
 * on the record's own `revision_no` (a bug just fixed - it must share one
 * cache entry with the detail page and refetch when a revision lands),
 * loading/empty/error pass straight through to RevisionsSection, the PDF
 * button sends `{revision_id}`, and the Excel button for stock inquiries
 * loads its exporter via a dynamic import.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';

const useStockInquiryMock = vi.fn();
const useStockInquiryRevisionsMock = vi.fn();
const useExportStockInquiryPdfMock = vi.fn();
vi.mock(
  '@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries',
  () => ({
    useStockInquiry: (...a: unknown[]) => useStockInquiryMock(...a),
    useStockInquiryRevisions: (...a: unknown[]) => useStockInquiryRevisionsMock(...a),
    useExportStockInquiryPdf: (...a: unknown[]) => useExportStockInquiryPdfMock(...a),
  }),
);

const usePurchaseRequestMock = vi.fn();
const usePurchaseRequestRevisionsMock = vi.fn();
const useExportPurchaseRequestPdfMock = vi.fn();
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests',
  () => ({
    usePurchaseRequest: (...a: unknown[]) => usePurchaseRequestMock(...a),
    usePurchaseRequestRevisions: (...a: unknown[]) => usePurchaseRequestRevisionsMock(...a),
    useExportPurchaseRequestPdf: (...a: unknown[]) => useExportPurchaseRequestPdfMock(...a),
  }),
);

vi.mock('@/hooks/useLookupOptionsByBinding', () => ({
  useLookupOptionsByBinding: () => ({ data: { options: [] } }),
}));

const exportStockInquiryRevisionToExcelMock = vi.fn().mockResolvedValue(undefined);
vi.mock(
  '@/app/(protected)/procurement-management/stock-inquiries/utils/exportStockInquiryToExcel',
  () => ({
    exportStockInquiryRevisionToExcel: (...a: unknown[]) =>
      exportStockInquiryRevisionToExcelMock(...a),
  }),
);

const createSalesTypeLabelResolverMock = vi.fn(
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  (_options?: unknown) => (code?: string | null) => code ?? null,
);
const exportPurchaseRequestOrSponsorshipRevisionToExcelMock = vi
  .fn()
  .mockResolvedValue(undefined);
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/lib/purchase-request-excel-export',
  () => ({
    createSalesTypeLabelResolver: (...a: unknown[]) =>
      createSalesTypeLabelResolverMock(...a),
    exportPurchaseRequestOrSponsorshipRevisionToExcel: (...a: unknown[]) =>
      exportPurchaseRequestOrSponsorshipRevisionToExcelMock(...a),
  }),
);

import FormRevisionsTab from './FormRevisionsTab';

function entry(overrides: Partial<FormRevisionEntry> = {}): FormRevisionEntry {
  return {
    id: overrides.id ?? 'rev-1',
    version_no: overrides.version_no ?? 1,
    revision_no: overrides.revision_no ?? 1,
    kind: overrides.kind ?? 'revision',
    label: overrides.label ?? 'Revision 1',
    reason: overrides.reason ?? 'Wrong quantity',
    submitted_at: overrides.submitted_at ?? '2026-07-01T02:00:00',
    submitted_by: overrides.submitted_by ?? 'Alex Tan',
    ...overrides,
  };
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  // Mirror the real hooks' `enabled: !!id` shape: a hook called with `null`
  // (the branch not serving this kind) never resolves data.
  useStockInquiryMock.mockImplementation((id: string | null) => ({
    data: id ? { id, revision_no: 0 } : undefined,
    isLoading: false,
  }));
  usePurchaseRequestMock.mockImplementation((id: string | null) => ({
    data: id ? { id, revision_no: 0, sales_type: 'demo' } : undefined,
    isLoading: false,
  }));
  useStockInquiryRevisionsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
  usePurchaseRequestRevisionsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
  useExportStockInquiryPdfMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
  useExportPurchaseRequestPdfMock.mockReturnValue({ mutate: vi.fn(), isPending: false });
});

describe('FormRevisionsTab - hook routing by kind', () => {
  it('reads the stock-inquiry lineage for kind=stock_inquiry and leaves the purchase-request hook idle', () => {
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(useStockInquiryMock).toHaveBeenCalledWith('si-1');
    expect(usePurchaseRequestMock).toHaveBeenCalledWith(null);
    expect(useStockInquiryRevisionsMock).toHaveBeenCalledWith('si-1', 0);
    expect(usePurchaseRequestRevisionsMock).toHaveBeenCalledWith(null, 0);
  });

  it('reads the shared purchase-request lineage for kind=purchase_request and leaves stock-inquiry idle', () => {
    render(<FormRevisionsTab kind="purchase_request" entityId="pr-1" />);

    expect(usePurchaseRequestMock).toHaveBeenCalledWith('pr-1');
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
    expect(usePurchaseRequestRevisionsMock).toHaveBeenCalledWith('pr-1', 0);
    expect(useStockInquiryRevisionsMock).toHaveBeenCalledWith(null, 0);
  });

  it('routes kind=sponsorship_form through the SAME purchase-request lineage as purchase_request', () => {
    render(<FormRevisionsTab kind="sponsorship_form" entityId="sf-1" />);

    expect(usePurchaseRequestMock).toHaveBeenCalledWith('sf-1');
    expect(useStockInquiryMock).toHaveBeenCalledWith(null);
    expect(usePurchaseRequestRevisionsMock).toHaveBeenCalledWith('sf-1', 0);
  });
});

describe('FormRevisionsTab - lineage query keyed on revision_no', () => {
  it('keys the stock-inquiry lineage query with the live record\'s own revision_no', () => {
    useStockInquiryMock.mockReturnValue({ data: { id: 'si-1', revision_no: 3 }, isLoading: false });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(useStockInquiryRevisionsMock).toHaveBeenCalledWith('si-1', 3);
  });

  it('keys the purchase-request lineage query with the live record\'s own revision_no', () => {
    usePurchaseRequestMock.mockReturnValue({
      data: { id: 'pr-1', revision_no: 5, sales_type: 'demo' },
      isLoading: false,
    });
    render(<FormRevisionsTab kind="purchase_request" entityId="pr-1" />);

    expect(usePurchaseRequestRevisionsMock).toHaveBeenCalledWith('pr-1', 5);
  });

  it('falls back to revision_no 0 while the live record has not loaded yet', () => {
    useStockInquiryMock.mockReturnValue({ data: undefined, isLoading: true });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(useStockInquiryRevisionsMock).toHaveBeenCalledWith('si-1', 0);
  });
});

describe('FormRevisionsTab - loading / empty / error pass through to RevisionsSection', () => {
  it('shows the loading skeleton state while the lineage query is in flight', () => {
    useStockInquiryRevisionsMock.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(screen.getByText('Revisions')).toBeInTheDocument();
    expect(
      screen.queryByText('No revisions - this is the original submission.'),
    ).not.toBeInTheDocument();
    expect(screen.queryByText('Could not load revisions.')).not.toBeInTheDocument();
  });

  it('shows the explicit empty state with an empty lineage', () => {
    useStockInquiryRevisionsMock.mockReturnValue({ data: [], isLoading: false, isError: false });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(
      screen.getByText('No revisions - this is the original submission.'),
    ).toBeInTheDocument();
  });

  it('reports a load failure rather than claiming there are no revisions', () => {
    useStockInquiryRevisionsMock.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(screen.getByText('Could not load revisions.')).toBeInTheDocument();
  });

  it('renders the timeline once the lineage query resolves with entries', () => {
    useStockInquiryRevisionsMock.mockReturnValue({
      data: [entry({ id: 'rev-1', label: 'Revision 1' })],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(screen.getByText('Revision 1')).toBeInTheDocument();
  });
});

describe('FormRevisionsTab - per-entry PDF export', () => {
  it('sends {revision_id: entry.id} through the stock-inquiry PDF export mutation', () => {
    const mutate = vi.fn();
    useExportStockInquiryPdfMock.mockReturnValue({ mutate, isPending: false });
    useStockInquiryRevisionsMock.mockReturnValue({
      data: [entry({ id: 'rev-9' })],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    fireEvent.click(screen.getByTestId('revision-export-pdf'));

    expect(mutate).toHaveBeenCalledWith({ id: 'si-1', options: { revision_id: 'rev-9' } });
  });

  it('sends {revision_id: entry.id} through the purchase-request PDF export mutation', () => {
    const mutate = vi.fn();
    useExportPurchaseRequestPdfMock.mockReturnValue({ mutate, isPending: false });
    usePurchaseRequestRevisionsMock.mockReturnValue({
      data: [entry({ id: 'rev-7' })],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="purchase_request" entityId="pr-1" />);

    fireEvent.click(screen.getByTestId('revision-export-pdf'));

    expect(mutate).toHaveBeenCalledWith({ id: 'pr-1', options: { revision_id: 'rev-7' } });
  });
});

describe('FormRevisionsTab - per-entry Excel export', () => {
  it('loads the stock-inquiry exporter via a dynamic import and exports the chosen entry against the live record', async () => {
    useStockInquiryMock.mockReturnValue({ data: { id: 'si-1', revision_no: 1 }, isLoading: false });
    const revisionEntry = entry({ id: 'rev-1' });
    useStockInquiryRevisionsMock.mockReturnValue({
      data: [revisionEntry],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    fireEvent.click(screen.getByTestId('revision-export-excel'));

    await waitFor(() =>
      expect(exportStockInquiryRevisionToExcelMock).toHaveBeenCalledWith(
        revisionEntry,
        { id: 'si-1', revision_no: 1 },
      ),
    );
  });

  it('disables the Excel button until the live record has loaded', () => {
    useStockInquiryMock.mockReturnValue({ data: undefined, isLoading: true });
    useStockInquiryRevisionsMock.mockReturnValue({
      data: [entry({ id: 'rev-1' })],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="stock_inquiry" entityId="si-1" />);

    expect(screen.getByTestId('revision-export-excel')).toBeDisabled();
    expect(exportStockInquiryRevisionToExcelMock).not.toHaveBeenCalled();
  });

  it('exports the purchase-request/sponsorship entry through the shared exporter with the resolved sales-type label', async () => {
    usePurchaseRequestMock.mockReturnValue({
      data: { id: 'pr-1', revision_no: 1, sales_type: 'demo' },
      isLoading: false,
    });
    const revisionEntry = entry({ id: 'rev-1', snapshot: { sales_type: 'promo' } });
    usePurchaseRequestRevisionsMock.mockReturnValue({
      data: [revisionEntry],
      isLoading: false,
      isError: false,
    });
    render(<FormRevisionsTab kind="purchase_request" entityId="pr-1" />);

    fireEvent.click(screen.getByTestId('revision-export-excel'));

    await waitFor(() =>
      expect(exportPurchaseRequestOrSponsorshipRevisionToExcelMock).toHaveBeenCalledWith(
        revisionEntry,
        { id: 'pr-1', revision_no: 1, sales_type: 'demo' },
        'promo',
      ),
    );
    // Never touches the stock-inquiry exporter's dynamic import.
    expect(exportStockInquiryRevisionToExcelMock).not.toHaveBeenCalled();
  });
});
