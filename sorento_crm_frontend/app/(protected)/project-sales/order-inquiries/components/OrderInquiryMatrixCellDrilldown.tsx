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
import type { OrderInquiryMatrixCell } from '../../_shared/types/orderInquiry.types';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

/**
 * The rows behind one matrix cell, in the same columns as the worklist - the generalised
 * replacement for the day-grid calendar's `OrderInquiryDayDrilldown`.
 *
 * A dialog, the way the fulfilment board opens a cell (the captain, 27 Aug): the panel
 * used to mount UNDER the matrix, and below the fold of a wide schedule nobody saw it
 * open. A modal sits on top of the cell that was pressed.
 *
 * No fetch of its own: the matrix already holds every filtered worklist row in memory
 * (`buildOrderInquiryMatrix`), so a cell's own `rows` ARE the drilldown's rows. Reusing
 * them rather than asking the server again means the grid and the drilldown can never
 * disagree about which rows are in a cell.
 */
export function OrderInquiryMatrixCellDrilldown({
  cell,
  rowLabel,
  bucketLabel,
  onClose,
}: {
  cell: OrderInquiryMatrixCell;
  rowLabel: string;
  bucketLabel: string;
  onClose: () => void;
}) {
  const columns = useOrderInquiryWorklistColumns();
  const rowCount = cell.rows.length;
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
          <PanelDataGrid
            title={`${rowCount} ${rowCount === 1 ? 'row' : 'rows'}`}
            columns={columns}
            rows={cell.rows}
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
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
