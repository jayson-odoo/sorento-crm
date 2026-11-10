'use client';

import * as React from 'react';
import { RecordHistory } from '@/components/history/RecordHistory';
import { useOrderInquiryHistory } from '../../../_shared/hooks/useOrderInquiry';

/** STANDARD-HISTORY wave 1: what each OI history `kind` reads as, in the Event filter and on
 * its badge (AC-SH-B8). The kinds are the backend's (`order_inquiry_history_service.py`). */
export const ORDER_INQUIRY_HISTORY_KINDS: Record<string, string> = {
  raised: 'Raised',
  reconfirmed: 'Reconfirmed',
  confirmed: 'Confirmed',
  unconfirmed: 'Unconfirmed',
  linked: 'Linked',
  unlinked: 'Unlinked',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
  reserved: 'Reserved',
  unreserved: 'Unreserved',
};

const TONES = {
  confirmed: 'success',
  unconfirmed: 'warning',
  linked: 'info',
  unlinked: 'warning',
  rejected: 'destructive',
  cancelled: 'destructive',
  reserved: 'info',
} as const;

/**
 * One OI's history (the detail page's History tab), or, given `rowIds`, only what touched
 * those rows (the line dialog's "All events" tab, AC-SH-B12): an event that touched other
 * rows too keeps its title ("Unconfirmed 9 lines") and lists only this line's rows.
 */
export function OrderInquiryHistory({
  inquiryId,
  rowIds,
}: {
  inquiryId: string | undefined;
  rowIds?: string[];
}) {
  const history = useOrderInquiryHistory(inquiryId);
  const events = React.useMemo(() => {
    const all = history.data?.events ?? [];
    if (!rowIds) return all;
    const mine = new Set(rowIds);
    return all
      .map((event) => ({ ...event, lines: event.lines.filter((line) => mine.has(line.row_id)) }))
      .filter((event) => event.lines.length > 0);
  }, [history.data, rowIds]);

  return (
    <RecordHistory
      events={events}
      kindLabels={ORDER_INQUIRY_HISTORY_KINDS}
      kindTones={TONES}
      isLoading={history.isLoading}
      isError={history.isError}
      onRetry={() => void history.refetch()}
      lineFilters={!rowIds}
    />
  );
}
