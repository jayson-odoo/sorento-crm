'use client';

import {
  OrderInquiryLinkCell,
  orderInquiryLinkEntries,
} from '@/app/(protected)/project-sales/_shared/components/OrderInquiryLinkCell';
import type { OrderInquiryWorklistRow } from '@/app/(protected)/project-sales/_shared/types/orderInquiry.types';

/** The Sales Order Lines tab's OI entries (`orderInquiryLinkEntries`, the shared cell's own). */
export const soLineInquiryEntries = orderInquiryLinkEntries;

/**
 * The Sales Order Lines tab's Order inquiry cell: the shared `OrderInquiryLinkCell`
 * (SPARE-PART-OR-B U3.1), under the test ids this tab has always carried.
 */
export function SoLineOrderInquiryCell({
  rows,
  lineId,
}: {
  rows: OrderInquiryWorklistRow[] | null | undefined;
  lineId: string;
}) {
  return <OrderInquiryLinkCell rows={rows} lineId={lineId} testIdPrefix="so-line-oi" />;
}
