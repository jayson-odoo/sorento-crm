'use client';

import { useState } from 'react';
import { FileDown, Printer } from 'lucide-react';
import { toast } from '@/lib/toast';

import { Button } from '@/components/ui/button';
import { RevisionsSection } from '@/components/common/RevisionsSection';
import type { FormRevisionEntry } from '@/components/common/RevisionTimeline';
import { useLookupOptionsByBinding } from '@/hooks/useLookupOptionsByBinding';
import {
  useStockInquiry,
  useStockInquiryRevisions,
  useExportStockInquiryPdf,
} from '@/app/(protected)/procurement-management/stock-inquiries/hooks/useStockInquiries';
import {
  usePurchaseRequest,
  usePurchaseRequestRevisions,
  useExportPurchaseRequestPdf,
} from '@/app/(protected)/procurement-management/purchase-requests/hooks/usePurchaseRequests';
import {
  createSalesTypeLabelResolver,
  exportPurchaseRequestOrSponsorshipRevisionToExcel,
} from '@/app/(protected)/procurement-management/purchase-requests/lib/purchase-request-excel-export';

/**
 * The "Revisions" tab on an office detail page (UAC H2, round 6).
 *
 * Self-fetching: Radix unmounts an inactive `TabsContent`, so this mounts when
 * the tab is opened and reads the record and its lineage itself rather than
 * being handed queries the Details tab owns. Both reads share the detail page's
 * OWN query keys - `['stock-inquiry', id]` and
 * `['stock-inquiry-revisions', id, revisionNo]` (`purchase-request` likewise) -
 * so React Query serves them from cache instead of issuing a second request.
 * Threading them down instead would mean changing
 * `FormDetailTabsWithRevisions` for every form that uses it, including the ones
 * with no revisions at all.
 *
 * The live record is read first because the lineage key needs its `revision_no`:
 * the revision queries are deliberately keyed on the record's changing field, so
 * a revision landing while this tab is open refetches the timeline instead of
 * serving the pre-revision lineage. Passing no revision number would both miss
 * that refetch AND open a second cache entry beside the detail page's.
 *
 * The record is needed anyway: exporting a revision needs identity (the id, the
 * type, the bare document number) that a snapshot does not carry.
 *
 * Purchase requests and sponsorship forms are ONE backend route
 * (`/purchase-requests/{id}/revisions`), so both map to the same hook.
 */
export type FormRevisionsKind =
  | 'stock_inquiry'
  | 'purchase_request'
  | 'sponsorship_form';

interface FormRevisionsTabProps {
  kind: FormRevisionsKind;
  entityId: string;
}

export default function FormRevisionsTab({ kind, entityId }: FormRevisionsTabProps) {
  const isStockInquiry = kind === 'stock_inquiry';
  // Both hooks of each pair are called unconditionally (rules of hooks); the one
  // that does not serve this kind is disabled by a null id and never fires a
  // request.
  const inquiry = useStockInquiry(isStockInquiry ? entityId : null);
  const request = usePurchaseRequest(isStockInquiry ? null : entityId);

  // The record's own revision counter keys the lineage read - the same value the
  // detail page keys it on, so the two share one cache entry and both refetch
  // the moment a new revision lands.
  const stockInquiryQuery = useStockInquiryRevisions(
    isStockInquiry ? entityId : null,
    Number(inquiry.data?.revision_no ?? 0),
  );
  const requestQuery = usePurchaseRequestRevisions(
    isStockInquiry ? null : entityId,
    Number(request.data?.revision_no ?? 0),
  );
  const query = isStockInquiry ? stockInquiryQuery : requestQuery;

  const salesTypeOptions = useLookupOptionsByBinding('purchase_requests', 'sales_type', {
    enabled: !isStockInquiry,
  });

  const exportInquiryPdf = useExportStockInquiryPdf();
  const exportRequestPdf = useExportPurchaseRequestPdf();
  const [exportingId, setExportingId] = useState<string | null>(null);

  const liveRecord = isStockInquiry ? inquiry.data : request.data;

  const exportPdf = (entry: FormRevisionEntry) => {
    const variables = { id: entityId, options: { revision_id: entry.id } };
    if (isStockInquiry) exportInquiryPdf.mutate(variables);
    else exportRequestPdf.mutate(variables);
  };

  const exportExcel = async (entry: FormRevisionEntry) => {
    if (!liveRecord) return;
    setExportingId(entry.id);
    try {
      if (isStockInquiry) {
        // Loaded on demand: the stock inquiry exporter pulls in ExcelJS, and a
        // static import would put that whole library in the purchase-request and
        // sponsorship-form bundles, which never call it.
        const { exportStockInquiryRevisionToExcel } = await import(
          '@/app/(protected)/procurement-management/stock-inquiries/utils/exportStockInquiryToExcel'
        );
        await exportStockInquiryRevisionToExcel(entry, inquiry.data!);
      } else {
        // The label is resolved from the REVISION's own code, not the live one:
        // a version submitted under a different sales type must read as that
        // type, not as today's.
        const resolve = createSalesTypeLabelResolver(salesTypeOptions.data?.options);
        const code =
          (entry.snapshot?.sales_type as string | null | undefined) ??
          request.data!.sales_type;
        await exportPurchaseRequestOrSponsorshipRevisionToExcel(
          entry,
          request.data!,
          resolve(code),
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Export failed');
    } finally {
      setExportingId(null);
    }
  };

  return (
    <RevisionsSection
      entries={query.data}
      isLoading={query.isLoading}
      isError={query.isError}
      entryActions={(entry) => (
        <>
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="revision-export-pdf"
            onClick={() => exportPdf(entry)}
          >
            <Printer className="size-4" />
            PDF
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            data-testid="revision-export-excel"
            disabled={!liveRecord || exportingId === entry.id}
            onClick={() => exportExcel(entry)}
          >
            <FileDown className="size-4" />
            {exportingId === entry.id ? 'Exporting…' : 'Excel'}
          </Button>
        </>
      )}
    />
  );
}
