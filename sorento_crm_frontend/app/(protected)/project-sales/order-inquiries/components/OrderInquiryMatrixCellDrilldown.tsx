'use client';

import * as React from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import type { OrderInquiryMatrixCell } from '../../_shared/types/orderInquiry.types';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

/**
 * The rows behind one matrix cell, in the same columns as the worklist above it - the
 * generalised replacement for the day-grid calendar's `OrderInquiryDayDrilldown`.
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

  return (
    <PanelDataGrid
      title={`${rowLabel} · ${bucketLabel}`}
      toolbar={
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          <X className="size-4" aria-hidden />
          Close
        </Button>
      }
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
    />
  );
}
