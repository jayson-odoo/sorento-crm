'use client';

import * as React from 'react';

import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrderInquiryWorklist } from '../../_shared/hooks/useOrderInquiry';
import { periodEnd } from '../../_shared/services/orderInquiryMatrixService';
import type {
  OrderInquiryMatrixAxis,
  OrderInquiryMatrixCell,
  OrderInquiryMatrixGranularity,
  OrderInquiryWorklistParams,
} from '../../_shared/types/orderInquiry.types';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

/**
 * The rows behind one matrix cell, in the same columns as the worklist - the generalised
 * replacement for the day-grid calendar's `OrderInquiryDayDrilldown`.
 *
 * A dialog, the way the fulfilment board opens a cell (the captain, 27 Aug): the panel
 * used to mount UNDER the matrix, and below the fold of a wide schedule nobody saw it
 * open. A modal sits on top of the cell that was pressed.
 *
 * S3: the matrix no longer carries a cell's own rows - the server groups them and answers
 * only the sums (PLAN section 3, "the drilldown keeps calling the list"). So this asks
 * the SAME list the worklist itself reads, scoped to this cell's own bucket
 * (`delivery_from`/`delivery_to`) and to the cell's OWN axis value (`axis`/`axis_key`,
 * equality on the very column the matrix grouped by).
 *
 * NOT through the search box (SF-2). It used to send `query = cell.axis_label`, which
 * threw away whatever the user had typed in the toolbar - so a cell opened while a
 * search was running showed rows that search excluded - and matched a fuzzy `ILIKE` on
 * a printed label two products can share.
 */
export function OrderInquiryMatrixCellDrilldown({
  cell,
  axis = 'product',
  granularity,
  filters,
  rowLabel,
  bucketLabel,
  onClose,
}: {
  cell: OrderInquiryMatrixCell;
  /** The axis the matrix grouped by - what `cell.axis_key` is a key OF. Defaults to the
   * matrix's own default axis, so the cell and its drilldown cannot read two columns. */
  axis?: OrderInquiryMatrixAxis;
  granularity: OrderInquiryMatrixGranularity;
  /** The list filters already narrowing the matrix (month, supplier, ack, kind, ...) -
   * every one of them still applies to what a cell drills down to. */
  filters: OrderInquiryWorklistParams;
  rowLabel: string;
  bucketLabel: string;
  onClose: () => void;
}) {
  const columns = useOrderInquiryWorklistColumns();
  const params = React.useMemo<OrderInquiryWorklistParams>(
    () => ({
      ...filters,
      axis,
      axis_key: cell.axis_key,
      delivery_from: cell.period,
      delivery_to: periodEnd(cell.period, granularity),
      limit: 1000,
    }),
    [filters, axis, cell.axis_key, cell.period, granularity],
  );
  const list = useOrderInquiryWorklist(params, { enabled: true });
  const rows = list.data?.data ?? [];
  const rowCount = list.data?.total ?? rows.length;
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        data-testid="matrix-cell-dialog-content"
        className="flex max-h-[85vh] w-full flex-col overflow-hidden p-0 sm:max-w-6xl"
      >
        <DialogHeader className="shrink-0 border-b p-4 sm:p-6">
          <DialogTitle className="min-w-0 break-words">{`${rowLabel} · ${bucketLabel}`}</DialogTitle>
          <DialogDescription className="sr-only">
            {`${rowCount} ${rowCount === 1 ? 'row' : 'rows'} in this cell`}
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
          {list.isLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            <PanelDataGrid
              title={`${rowCount} ${rowCount === 1 ? 'row' : 'rows'}`}
              columns={columns}
              rows={rows}
              getRowId={(row) => row.id}
              listingKey="projects.projects.view::order-inquiry-worklist-cell"
              emptyTitle="Nothing in this cell"
              searchPlaceholder="Search S/O, item, product or customer…"
              searchOf={(row) =>
                [row.so_number, row.item_code, row.product_name, row.project_customer]
                  .filter(Boolean)
                  .join(' ')
              }
              pageSize={10}
              // The DialogBody above already owns the scroll viewport (overflow-y-auto).
              scrollerMaxHeight={false}
            />
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
