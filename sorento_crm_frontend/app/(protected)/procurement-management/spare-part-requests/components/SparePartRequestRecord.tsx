'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import type { RowSelectionState } from '@tanstack/react-table';
import { useQuery } from '@tanstack/react-query';
import { FileText, History, ListOrdered, Timer } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RecordHeaderCard } from '@/components/common/RecordHeaderCard';
import BackToList from '@/components/common/BackToList';
import DetailActions from '@/components/common/DetailActions';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import FormSLATrackingTab from '@/app/(protected)/sla-management/_shared/FormSLATrackingTab';
import { getFormSLATrackers } from '@/app/(protected)/sla-management/_shared/formSLAService';
import { SlaActiveTrackerControls } from '@/app/(protected)/sla-management/_shared/SlaActiveTrackerControls';
import { OrderInquiryLinesTab } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLinesTab';
import { SparePartRequestGeneralCards } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryGeneralTab';
import { OrderInquiryHistory } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryHistory';
import { OrderInquiryLineHistoryDialog } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLineHistoryDialog';
import { SparePartRequestActions } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/SparePartRequestActions';
import type { SparePartLineEdit } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/orderInquiryHeaderLinesColumns';
import { useOrderInquiryHeaderLines } from '@/app/(protected)/project-sales/_shared/hooks/useOrderInquiry';
import {
  sparePartRequestsPagerQuery,
  useEditSparePartLine,
  useSparePartRequest,
} from '@/app/(protected)/project-sales/_shared/hooks/useSparePartRequest';
import {
  SPARE_PART_REQUESTS_PATH,
  canEditSparePartPhotos,
  isPreApproval,
  sparePartRequestStatusLabel,
  sparePartStateVariant,
} from '@/app/(protected)/project-sales/_shared/lib/sparePartRequest';
import type { OrderInquiryLine } from '@/app/(protected)/project-sales/_shared/lib/orderInquiryLineFold';
import type { OrderInquiryWorklistRow } from '@/app/(protected)/project-sales/_shared/types/orderInquiry.types';

const NO_ROWS: OrderInquiryWorklistRow[] = [];

/**
 * SPARE-PART-ORDER-REQUEST (hand-test round G3): a spare part request's own record page. The
 * header card (number, status pill, the request's moves), then Lines, General and History, all
 * the same pieces the Order Inquiry page shows a spare part request with. Once approved it
 * links to the order inquiry purchasing works it on.
 *
 * Hand-test round 2 (owner 13 Nov): who acts next is shown the way Complaint shows it, the
 * escalation / extension banner above the tabs and an SLA Tracking tab holding the shared
 * tracker grid while an approval stage is open (assignee, stage, due).
 */
export function SparePartRequestRecord({ id }: { id: string }) {
  const requestQuery = useSparePartRequest(id);
  const linesQuery = useOrderInquiryHeaderLines(id);
  const editLine = useEditSparePartLine(id);
  const [tab, setTab] = useState('lines');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [historyLine, setHistoryLine] = useState<OrderInquiryLine | null>(null);
  const request = requestQuery.data;
  const revisionState = request?.revision_state ?? null;
  // U4.6: while a revision is open this page reads its qtys (the request's own `lines[].qty`);
  // the rows themselves, and the order inquiry, keep the approved qty.
  const lines = useMemo(() => {
    const rows = linesQuery.data ?? NO_ROWS;
    if (!revisionState || !request) return rows;
    const revised = new Map(request.lines.map((line) => [line.id, line.qty]));
    return rows.map((row) => (revised.has(row.id) ? { ...row, qty: revised.get(row.id) } : row));
  }, [linesQuery.data, request, revisionState]);
  // The same key FormSLATrackingTab reads, so the tab and the banner share one request.
  const { data: slaTrackers } = useQuery({
    queryKey: ['form-sla-trackers', 'spare_part_request', id],
    queryFn: () => getFormSLATrackers('spare_part_request', id),
    enabled: Boolean(id),
  });
  const activeTracker =
    (Array.isArray(slaTrackers) ? slaTrackers : []).find((t) => !t.is_resolved) ?? null;
  const onEditLine = useCallback(
    (row: OrderInquiryWorklistRow, edit: SparePartLineEdit) =>
      editLine.mutate({ rowId: row.id, edit }),
    [editLine],
  );

  if (requestQuery.isLoading) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading the request">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (requestQuery.isError || !request) {
    return (
      <Card className="flex flex-col items-center gap-3 p-10 text-center">
        <div className="text-sm font-semibold">Could not load this order request</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {requestQuery.error instanceof Error
            ? requestQuery.error.message
            : 'Try again in a moment.'}
        </p>
        <BackToList listPath={SPARE_PART_REQUESTS_PATH} label="Back to order requests" />
      </Card>
    );
  }

  const raised = !isPreApproval(request.state) && request.state !== 'cancelled';
  const showActions = request.can_decide || request.can_edit || request.can_revise;

  return (
    <div className="space-y-4">
      <RecordHeaderCard
        title={request.inquiry_no ?? 'Order request'}
        badges={
          // U4.6: an open revision's own state, else the request's.
          <Badge
            variant={sparePartStateVariant(revisionState ?? request.state)}
            appearance="light"
            size="md"
          >
            {sparePartRequestStatusLabel(revisionState ?? request.state)}
          </Badge>
        }
        subtitle={[
          `Requested by ${request.requested_by_name ?? 'Not recorded'}${
            request.submitted_at
              ? `, submitted ${formatDateTimeInMalaysia(request.submitted_at)}`
              : ''
          }`,
          raised ? (
            <Link
              href={`/project-sales/order-inquiries/${request.id}`}
              className="font-medium text-primary hover:underline"
            >
              Raised to purchasing
            </Link>
          ) : null,
        ]}
        actions={
          <DetailActions
            pager={{
              ...sparePartRequestsPagerQuery,
              detailPath: SPARE_PART_REQUESTS_PATH,
              currentId: id,
              ariaLabel: 'order request',
            }}
            primary={
              showActions ? <SparePartRequestActions header={request} rows={lines} /> : undefined
            }
          />
        }
      />

      <SlaActiveTrackerControls activeTracker={activeTracker} />

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start">
          <TabsTrigger value="lines">
            <ListOrdered />
            <span>Lines</span>
          </TabsTrigger>
          <TabsTrigger value="general">
            <FileText />
            <span>General</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            <History />
            <span>History</span>
          </TabsTrigger>
          <TabsTrigger value="sla">
            <Timer />
            <span>SLA Tracking</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="lines" className="mt-0 focus-visible:outline-none">
          <OrderInquiryLinesTab
            lines={lines}
            isLoading={linesQuery.isLoading}
            error={linesQuery.error}
            onRetry={() => void linesQuery.refetch()}
            rowSelection={rowSelection}
            onRowSelectionChange={setRowSelection}
            onLineHistoryClick={setHistoryLine}
            sparePart={{
              view: 'request',
              headerState: request.state,
              revisionState,
              canEditRevision: Boolean(request.can_edit),
              canDecide: Boolean(request.can_decide),
              canEditPhotos: canEditSparePartPhotos(request),
              currency: request.currency,
              onEditLine,
            }}
          />
        </TabsContent>

        <TabsContent value="general" className="mt-0 space-y-4 focus-visible:outline-none">
          <SparePartRequestGeneralCards header={request} />
        </TabsContent>

        <TabsContent value="history" className="mt-0 focus-visible:outline-none">
          <OrderInquiryHistory inquiryId={id} />
        </TabsContent>

        <TabsContent value="sla" className="mt-0 focus-visible:outline-none">
          {activeTracker ? (
            <FormSLATrackingTab sourceEntityType="spare_part_request" sourceEntityId={id} />
          ) : (
            <Card className="flex flex-col items-center gap-1 p-10 text-center">
              <div className="text-sm font-semibold">No approval stage is open</div>
              <p className="text-sm text-muted-foreground">
                Who decides next shows here while the request waits for approval.
              </p>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {historyLine ? (
        <OrderInquiryLineHistoryDialog
          line={historyLine}
          onOpenChange={(next) => {
            if (!next) setHistoryLine(null);
          }}
        />
      ) : null}
    </div>
  );
}

export default SparePartRequestRecord;
