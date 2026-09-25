'use client';

import * as React from 'react';
import { Dialog, DialogBody, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import type { DecisionTrailEntry } from '../../../_shared/services/orderInquiryReserveService';

/**
 * `PLAN-oi-decision-trail-ui.md` (round 2, AC-DT-5/AC-DT-10) - the History icon's own
 * dialog, the same shape as `ReserveLineHistoryDialog` beside it: pure presentation, the
 * entries already resolved by the caller (`useDecisionTrail`) one layer up. Shared by the
 * OI worklist, the OI detail Lines tab and the fulfilment board, so a History icon on any
 * of the three opens the same trail for the same core sales-order line.
 */
const DECISION_TRAIL_KIND_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  saved: 'Saved',
  raised: 'Raised',
  reconfirmed: 'Reconfirmed',
  sheet: 'Sheet',
  planning_change: 'Planning change',
};

export function DecisionTrailDialog({
  open,
  onOpenChange,
  itemCode,
  entries,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  itemCode: string | null;
  entries: DecisionTrailEntry[];
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Decision trail{itemCode ? ` - ${itemCode}` : ''}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-2">
          {entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">No trail recorded yet.</p>
          ) : (
            entries.map((entry, index) => (
              // The entry's own identity - kind + when it happened - never the array
              // index, which reorders on refetch.
              <div
                key={`${entry.kind}-${entry.at ?? index}`}
                className="rounded-md border border-border p-2 text-xs"
              >
                <div className="font-medium">
                  {DECISION_TRAIL_KIND_LABEL[entry.kind] ?? entry.kind}
                  {entry.detail ? ` · ${entry.detail}` : ''}
                </div>
                <div className="text-muted-foreground">
                  {entry.actor_name ?? 'Unknown'}
                  {/* UTC on the wire: shown in Malaysia time, same as every other
                      timestamp on this screen. Absent on a `sheet` mark (AC-DT-6): nobody
                      in this system raised it, so no time is claimed either. */}
                  {entry.at ? ` on ${formatDateTimeInMalaysia(entry.at)}` : ''}
                </div>
              </div>
            ))
          )}
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

export default DecisionTrailDialog;
