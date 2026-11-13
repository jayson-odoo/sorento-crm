'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import type { RowSelectionState } from '@tanstack/react-table';
import { FileText, History, ListOrdered } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { RecordHeaderCard } from '@/components/common/RecordHeaderCard';
import BackToList from '@/components/common/BackToList';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { OrderInquiryLinesTab } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLinesTab';
import { SparePartRequestGeneralCards } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryGeneralTab';
import { OrderInquiryHistory } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryHistory';
import { OrderInquiryLineHistoryDialog } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/OrderInquiryLineHistoryDialog';
import { SparePartRequestActions } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/SparePartRequestActions';
import type { SparePartLineEdit } from '@/app/(protected)/project-sales/order-inquiries/[id]/components/orderInquiryHeaderLinesColumns';
import { useOrderInquiryHeaderLines } from '@/app/(protected)/project-sales/_shared/hooks/useOrderInquiry';
import {
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
import type {
  OrderInquiryLine,
  OrderInquiryWorklistRow,
} from '@/app/(protected)/project-sales/_shared/types/orderInquiry.types';

const NO_ROWS: OrderInquiryWorklistRow[] = [];

/**
 * SPARE-PART-ORDER-REQUEST (hand-test round G3): a spare part request's own record page. The
 * header card (number, status pill, the request's moves), then Lines, General and History, all
 * the same pieces the Order Inquiry page shows a spare part request with. Once approved it
 * links to the order inquiry purchasing works it on.
 */
export function SparePartRequestRecord({ id }: { id: string }) {
  const requestQuery = useSparePartRequest(id);
  const linesQuery = useOrderInquiryHeaderLines(id);
  const editLine = useEditSparePartLine(id);
  const [tab, setTab] = useState('lines');
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [historyLine, setHistoryLine] = useState<OrderInquiryLine | null>(null);
  const lines = useMemo(() => linesQuery.data ?? NO_ROWS, [linesQuery.data]);
  const onEditLine = useCallback(
    (row: OrderInquiryWorklistRow, edit: SparePartLineEdit) =>
      editLine.mutate({ rowId: row.id, edit }),
    [editLine],
  );

  const request = requestQuery.data;

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
        <div className="text-sm font-semibold">Could not load this spare part request</div>
        <p className="max-w-md text-sm text-muted-foreground">
          {requestQuery.error instanceof Error
            ? requestQuery.error.message
            : 'Try again in a moment.'}
        </p>
        <BackToList listPath={SPARE_PART_REQUESTS_PATH} label="Back to spare part requests" />
      </Card>
    );
  }

  const raised = !isPreApproval(request.state) && request.state !== 'cancelled';
  const showActions = request.can_decide || request.can_edit || request.can_revise;

  return (
    <div className="space-y-4">
      <RecordHeaderCard
        title={request.inquiry_no ?? 'Spare part request'}
        badges={
          <Badge variant={sparePartStateVariant(request.state)} appearance="light" size="md">
            {sparePartRequestStatusLabel(request.state)}
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
          showActions ? <SparePartRequestActions header={request} rows={lines} /> : undefined
        }
      />

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
              headerState: request.state,
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
