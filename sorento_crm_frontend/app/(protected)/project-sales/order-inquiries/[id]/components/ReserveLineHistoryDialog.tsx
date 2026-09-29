'use client';

import * as React from 'react';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { OrderInquiryReserveHistoryEntry } from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` section 6e.2 (round 4), AC-RS-89 - a reserved line's
 * reserve request history. Entries are already resolved by the caller
 * (`OrderInquiryDetail.tsx`, `useOrderInquiryRowHistory`) - this component is pure
 * presentation, UI -> hook -> service already having happened one layer up.
 *
 * `PLAN-oi-no-double-count-25sep.md` S0 (owner ruling 26 Sep, G3): no dialog of its own
 * any more - it is the Reserve tab of the line's one History dialog
 * (`OrderInquiryLineHistoryDialog`), and its icon is gone.
 */
const HISTORY_KIND_LABEL: Record<string, string> = {
  requested: 'Requested',
  reserved: 'Reserved',
  unreserved: 'Unreserved',
  cancelled: 'Request cancelled',
};

export function ReserveHistoryEntries({
  entries,
}: {
  entries: OrderInquiryReserveHistoryEntry[];
}) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No history yet.</p>;
  }
  return (
    <div className="space-y-2">
      {entries.map((entry, index) => (
        // The entry's own identity - kind + when it happened - never the array
        // index, which reorders on refetch.
        <div
          key={`${entry.kind}-${entry.created_at ?? index}`}
          className="rounded-md border border-border p-2 text-xs"
        >
          <div className="font-medium">
            {HISTORY_KIND_LABEL[entry.kind] ?? entry.kind}
            {entry.qty ? ` ${entry.qty}` : ''}
            {entry.location ? ` @ ${entry.location}` : ''}
          </div>
          <div className="text-muted-foreground">
            {entry.actor_name ?? 'Unknown'}
            {/* UTC on the wire (and naive UTC on older rows): shown in Malaysia
                time. `formatDateTime` strips the offset and would print UTC. */}
            {entry.created_at ? ` on ${formatDateTimeInMalaysia(entry.created_at)}` : ''}
            {entry.reason ? ` - ${entry.reason}` : ''}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ReserveHistoryEntries;
