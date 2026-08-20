'use client';

import * as React from 'react';
import { format, parseISO } from 'date-fns';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PanelDataGrid } from '../../_shared/components/PanelDataGrid';
import { useOrderInquiryWorklist } from '../../_shared/hooks/useOrderInquiry';
import type { OrderInquiryWorklistParams } from '../../_shared/types/orderInquiry.types';
import { useOrderInquiryWorklistColumns } from './orderInquiryWorklistColumns';

/**
 * The list a calendar day narrows to, in the same columns as the worklist above it (the
 * simpler of the two options considered - a slide-over would have needed its own column
 * set and its own empty/loading states for no real gain over showing the rows in place).
 *
 * There is no server filter for "delivery date exactly this day" - only the whole
 * delivery MONTH - so this asks for the day's own month at a generous page size and
 * narrows to the day client-side. A delivery month has never approached that many rows
 * in practice; if one ever does, the fix is a `delivery_date` filter on the worklist
 * route itself, not a bigger number here.
 */
const DAY_FETCH_LIMIT = 1000;

export function OrderInquiryDayDrilldown({
  day,
  monthFilters,
  onClose,
}: {
  /** `YYYY-MM-DD`. */
  day: string;
  /** Every worklist filter except `delivery_month`, which this pins to the day's own month. */
  monthFilters: Omit<OrderInquiryWorklistParams, 'delivery_month' | 'page' | 'limit' | 'sort' | 'dir'>;
  onClose: () => void;
}) {
  const params = React.useMemo<OrderInquiryWorklistParams>(
    () => ({
      ...monthFilters,
      delivery_month: day.slice(0, 7),
      limit: DAY_FETCH_LIMIT,
      sort: 'item_code',
      dir: 'asc',
    }),
    [monthFilters, day],
  );
  const list = useOrderInquiryWorklist(params);
  const rows = React.useMemo(
    () => (list.data?.data ?? []).filter((row) => row.delivery_date === day),
    [list.data, day],
  );
  const columns = useOrderInquiryWorklistColumns();
  const label = React.useMemo(() => {
    try {
      return format(parseISO(day), 'd MMMM yyyy');
    } catch {
      return day;
    }
  }, [day]);

  return (
    <PanelDataGrid
      title={`Due ${label}`}
      toolbar={
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>
          <X className="size-4" aria-hidden />
          Close
        </Button>
      }
      columns={columns}
      rows={rows}
      getRowId={(row) => row.id}
      listingKey="projects.projects.view::order-inquiry-worklist-day"
      isLoading={list.isLoading}
      error={list.isError ? list.error : undefined}
      emptyTitle="Nothing due this day"
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
