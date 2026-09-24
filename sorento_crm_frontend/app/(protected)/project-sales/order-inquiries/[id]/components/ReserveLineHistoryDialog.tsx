'use client';

import * as React from 'react';
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { OrderInquiryReserveHistoryEntry } from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-request-cs-reserve.md` section 6e.2 (round 4), AC-RS-89 - the former
 * History TAB of `ReserveRowDialog` (retired this round), now its own small read-only
 * dialog opened from the Lines grid's own `History` icon on a reserved line. Entries
 * are already resolved by the caller (`OrderInquiryDetail.tsx`, `useOrderInquiryRowHistory`)
 * - this component is pure presentation, UI -> hook -> service already having happened
 * one layer up.
 */
const HISTORY_KIND_LABEL: Record<string, string> = {
  requested: 'Requested',
  reserved: 'Reserved',
  unreserved: 'Unreserved',
  cancelled: 'Request cancelled',
};

export function ReserveLineHistoryDialog({
  open,
  onOpenChange,
  itemCode,
  entries,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  itemCode: string | null;
  entries: OrderInquiryReserveHistoryEntry[];
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>History{itemCode ? ` - ${itemCode}` : ''}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-2">
          {entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">No history yet.</p>
          ) : (
            entries.map((entry, index) => (
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
            ))
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default ReserveLineHistoryDialog;
