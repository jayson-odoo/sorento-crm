'use client';

import * as React from 'react';
import AuditTrail from '@/components/audit/AuditTrail';
import { useOrderInquiryHistory } from '../../../_shared/hooks/useOrderInquiry';
import type { OrderInquiryHistoryView } from '../../../_shared/services/orderInquiryService';

/**
 * STANDARD-HISTORY v2 (owner "ok", 10 Nov 2026): one OI's history in the ONE history
 * component, the Audit Trail (the PO / product History tab). Given `rowIds`, only what touched
 * those rows (the line dialog's History tab): an entry that touched other rows too keeps its
 * sentence ("Unconfirmed 9 lines, back to To confirm") and lists only this line's rows.
 * `view="inquiry"` (the OI page): an order request reads only what happened from its first
 * raise on; no `view` is the whole life (the order request page).
 */
export function OrderInquiryHistory({
  inquiryId,
  rowIds,
  view,
}: {
  inquiryId: string | undefined;
  rowIds?: string[];
  view?: OrderInquiryHistoryView;
}) {
  const history = useOrderInquiryHistory(inquiryId, view);
  const entries = React.useMemo(() => {
    const all = history.data?.events ?? [];
    if (!rowIds) return all;
    const mine = new Set(rowIds);
    return all
      .map((event) => ({ ...event, lines: event.lines.filter((line) => mine.has(line.row_id)) }))
      .filter((event) => event.lines.length > 0);
  }, [history.data, rowIds]);

  return (
    <AuditTrail
      title="History"
      entries={entries}
      isLoading={history.isLoading}
      isError={history.isError}
      onRetry={() => void history.refetch()}
    />
  );
}
